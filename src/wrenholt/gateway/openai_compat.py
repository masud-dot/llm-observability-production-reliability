"""Adapter for OpenAI-compatible endpoints, with SDK retries off.

Classification follows OpenAI's error-code guide: billing, spend
and usage limits arrive as 429 with their own error.code, and
retrying them cannot restore access, so they map to
quota_exhausted. Every other 429 is a rate limit.
"""

import copy
import math
from collections.abc import AsyncGenerator, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

import httpx2
import openai
from openai.types.chat import (
    ChatCompletionFunctionToolParam,
    ChatCompletionMessageFunctionToolCall,
    ChatCompletionMessageParam,
)

from wrenholt.gateway.errors import ErrorType, ProviderError
from wrenholt.gateway.routing import Route
from wrenholt.gateway.types import (
    Completion,
    Message,
    ToolCall,
    ToolSpec,
)

Choice = Literal["auto", "required"]

QUOTA_CODES = frozenset(
    {
        "insufficient_quota",
        "credit_balance_exhausted",
        "organization_spend_limit_exceeded",
        "project_spend_limit_exceeded",
        "organization_usage_limit_exceeded",
    }
)


def classify(
    status: int, code: str | None, kind: str | None
) -> ErrorType:
    """Map an HTTP error from an OpenAI-compatible API."""
    if status == 402 or code in QUOTA_CODES:
        return ErrorType.QUOTA_EXHAUSTED
    if kind == "insufficient_quota":
        return ErrorType.QUOTA_EXHAUSTED
    if status == 429:
        return ErrorType.RATE_LIMITED
    if status in (401, 403):
        return ErrorType.AUTH
    if status in (408, 504):
        return ErrorType.TIMEOUT
    if status in (503, 529):
        return ErrorType.OVERLOADED
    if status >= 500:
        return ErrorType.PROVIDER_UNAVAILABLE
    return ErrorType.INVALID_REQUEST


def retry_after(headers: Mapping[str, str]) -> float | None:
    """Seconds the provider asked for, if it said (HTTP dates
    are treated as absent)."""
    for name, scale in (
        ("retry-after-ms", 1000.0),
        ("retry-after", 1.0),
    ):
        value = headers.get(name)
        if value is None:
            continue
        try:
            seconds = float(value) / scale
        except ValueError:
            continue
        if math.isfinite(seconds) and seconds >= 0:
            return seconds
    return None


def to_openai(message: Message) -> ChatCompletionMessageParam:
    payload: dict[str, object] = {
        "role": message.role,
        "content": message.content,
    }
    if message.tool_calls:  # Chapter 9: the assistant called tools
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": call.arguments,
                },
            }
            for call in message.tool_calls
        ]
    if message.tool_call_id:  # a tool's answer to one call
        payload["tool_call_id"] = message.tool_call_id
    return cast(ChatCompletionMessageParam, payload)


def to_tool(spec: ToolSpec) -> ChatCompletionFunctionToolParam:
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": dict(spec.parameters),
        },
    }


def calls_of(
    calls: Sequence[object] | None,
) -> tuple[ToolCall, ...]:
    """Function calls in a response; Linnet offers no other kind."""
    return tuple(
        ToolCall(c.id, c.function.name, c.function.arguments)
        for c in calls or ()
        if isinstance(c, ChatCompletionMessageFunctionToolCall)
    )


class OpenAICompatible:
    def __init__(self, route: Route, timeout: float = 30.0) -> None:
        self._client = openai.AsyncOpenAI(
            base_url=route.base_url,
            api_key=route.api_key,
            max_retries=0,  # the gateway owns every retry
            timeout=timeout,
        )
        self._tools: tuple[ToolSpec, ...] = ()
        self._choice: Choice = "auto"

    def offering(
        self, tools: Sequence[ToolSpec], choice: Choice
    ) -> "OpenAICompatible":
        """The same client, offering tools with every whole (not
        streamed) request (Chapter 9)."""
        bound = copy.copy(self)
        bound._tools, bound._choice = tuple(tools), choice
        return bound

    def stream(
        self, model: str, messages: Sequence[Message]
    ) -> AsyncGenerator["Chunk"]:
        return chunks_of(self._client, model, messages)

    async def chat(
        self, model: str, messages: Sequence[Message]
    ) -> Completion:
        chat = self._client.chat.completions.with_raw_response
        tools = [to_tool(t) for t in self._tools] or openai.omit
        choice = self._choice if self._tools else openai.omit
        try:
            raw = await chat.create(
                model=model,
                messages=[to_openai(m) for m in messages],
                tools=tools,
                tool_choice=choice,
            )
        except openai.APITimeoutError as exc:
            raise ProviderError(ErrorType.TIMEOUT) from exc
        except openai.APIConnectionError as exc:
            raise ProviderError(
                ErrorType.PROVIDER_UNAVAILABLE
            ) from exc
        except openai.APIStatusError as exc:
            kind = classify(exc.status_code, exc.code, exc.type)
            wait = retry_after(exc.response.headers)
            raise ProviderError(kind, exc.status_code, wait) from exc
        response = raw.parse()
        usage = response.usage
        return Completion(
            text=response.choices[0].message.content or "",
            status=raw.status_code,
            response_model=response.model,
            response_id=response.id,
            finish_reasons=tuple(
                str(c.finish_reason) for c in response.choices
            ),
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
            tool_calls=calls_of(
                response.choices[0].message.tool_calls
            ),
        )

    async def aclose(self) -> None:
        await self._client.close()


@dataclass(frozen=True)
class Chunk:
    text: str
    finish_reason: str | None
    model: str


async def chunks_of(
    client: openai.AsyncOpenAI,
    model: str,
    messages: Sequence[Message],
) -> AsyncGenerator[Chunk]:
    """Chunks of one streamed completion (Chapter 8). Errors before
    the stream map as for chat. Once it has started, any failure,
    an error event after HTTP 200 included, is stream_interrupted."""
    try:
        events = await client.chat.completions.create(
            model=model,
            messages=[to_openai(m) for m in messages],
            stream=True,
        )
    except openai.APITimeoutError as exc:
        raise ProviderError(ErrorType.TIMEOUT) from exc
    except openai.APIConnectionError as exc:
        raise ProviderError(ErrorType.PROVIDER_UNAVAILABLE) from exc
    except openai.APIStatusError as exc:
        kind = classify(exc.status_code, exc.code, exc.type)
        wait = retry_after(exc.response.headers)
        raise ProviderError(kind, exc.status_code, wait) from exc
    try:
        async for event in events:
            choice = event.choices[0] if event.choices else None
            yield Chunk(
                (choice.delta.content or "") if choice else "",
                choice.finish_reason if choice else None,
                event.model,
            )
    except (openai.APIError, httpx2.HTTPError) as exc:
        raise ProviderError(ErrorType.STREAM_INTERRUPTED) from exc
    finally:
        await events.close()
