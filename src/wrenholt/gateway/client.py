"""The LLM gateway: every model call in Linnet goes through here.

One CLIENT span covers each logical request, retries included, as
the GenAI conventions ask; one INTERNAL child span records each
attempt; the HTTP client instrumentation, when on, adds a span
under each attempt.
"""

import asyncio
import contextlib
import copy
import random
import time
from collections.abc import (
    AsyncGenerator,
    Awaitable,
    Callable,
    Mapping,
    Sequence,
)
from dataclasses import dataclass

from opentelemetry import metrics, trace
from opentelemetry.context import Context
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from wrenholt.gateway.context import PROMPT
from wrenholt.gateway.errors import ErrorType, ProviderError
from wrenholt.gateway.openai_compat import (
    Choice,
    Chunk,
    OpenAICompatible,
)
from wrenholt.gateway.policy import RetryPolicy
from wrenholt.gateway.routing import Route
from wrenholt.gateway.streaming import StreamClock
from wrenholt.gateway.types import Completion, Message, ToolSpec
from wrenholt.telemetry import conventions as c

Attrs = dict[str, str | bool | int | float | list[str]]


@dataclass
class StreamResult:
    """How a stream ended, filled in for its caller (Chapter 8)."""

    response_model: str = ""
    chunks: int = 0
    first_chunk_s: float | None = None
    duration_s: float | None = None
    error: ProviderError | None = None
    cancelled: bool = False


def _undelivered(err: ProviderError) -> ProviderError:
    """How the retry policy judges a failure before any chunk has
    reached the caller: a broken stream is then just a failed
    attempt, judged like an unavailable provider."""
    if err.error_type is ErrorType.STREAM_INTERRUPTED:
        return ProviderError(
            ErrorType.PROVIDER_UNAVAILABLE,
            err.status,
            err.retry_after,
        )
    return err


async def _aclose(reply: AsyncGenerator[Chunk]) -> None:
    await reply.aclose()


class Gateway:
    def __init__(
        self,
        routes: Mapping[str, Route],
        policy: RetryPolicy | None = None,
        *,
        tracer_provider: trace.TracerProvider | None = None,
        meter_provider: metrics.MeterProvider | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
        pinned: Mapping[str, str] | None = None,
    ) -> None:
        self._routes = dict(routes)
        # Chapter 6: the response model each requested model should
        # return; anything else is a silent model change (FS-11).
        self._pinned = dict(pinned or {})
        self._adapters = {
            r: OpenAICompatible(r) for r in set(routes.values())
        }
        self._policy = policy or RetryPolicy()
        self._sleep, self._jitter = sleep, jitter
        self._tracer = trace.get_tracer(
            "wrenholt.gateway", tracer_provider=tracer_provider
        )
        meter = metrics.get_meter(
            "wrenholt.gateway", meter_provider=meter_provider
        )
        self._duration = meter.create_histogram(
            c.OPERATION_DURATION,
            unit="s",
            description="GenAI operation duration.",
            explicit_bucket_boundaries_advisory=c.DURATION_BUCKETS,
        )
        self._attempts = meter.create_counter(
            c.ATTEMPTS,
            unit="{attempt}",
            description="Provider attempts made by the gateway.",
        )
        # Chapter 8: what users feel in a streamed answer.
        self._ttfc = meter.create_histogram(
            c.TIME_TO_FIRST_CHUNK,
            unit="s",
            description="Time to receive the first chunk.",
            explicit_bucket_boundaries_advisory=c.TTFC_BUCKETS,
        )
        self._tpoc = meter.create_histogram(
            c.TIME_PER_OUTPUT_CHUNK,
            unit="s",
            description="Time per output chunk after the first.",
            explicit_bucket_boundaries_advisory=c.CHUNK_BUCKETS,
        )
        self._mismatches = meter.create_counter(
            c.MODEL_MISMATCHES,
            unit="{response}",
            description="Responses from a model other than the pin.",
        )

    def with_tools(
        self, tools: Sequence[ToolSpec], choice: Choice = "auto"
    ) -> "Gateway":
        """This gateway, offering tools with each chat request
        (Chapter 9), as the SDK's with_options returns a client with
        new options. Routes, retries and instruments are shared, so
        close the gateway, never the view."""
        view = copy.copy(self)
        view._adapters = {
            route: adapter.offering(tools, choice)
            for route, adapter in self._adapters.items()
        }
        return view

    async def chat(
        self, model: str, messages: Sequence[Message]
    ) -> Completion:
        route = self._routes[model]
        address, port = route.server
        base: Attrs = {
            c.OPERATION_NAME: c.CHAT,
            c.PROVIDER_NAME: route.provider,
            c.REQUEST_MODEL: model,
            c.SERVER_ADDRESS: address,
            c.SERVER_PORT: port,
        }
        start = time.perf_counter()
        with self._tracer.start_as_current_span(
            f"{c.CHAT} {model}",
            kind=SpanKind.CLIENT,
            attributes=base,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            attempt, delay = 0, 0.0
            while True:
                attempt += 1
                try:
                    result = await self._attempt(
                        route, model, messages, attempt, delay
                    )
                except ProviderError as err:
                    wait = self._policy.next_delay(
                        attempt, err, self._jitter()
                    )
                    if wait is None:
                        self._end(span, base, start, attempt, err=err)
                        raise
                    delay = wait
                    await self._sleep(delay)
                    continue
                self._end(span, base, start, attempt, result=result)
                return result

    async def _attempt(
        self,
        route: Route,
        model: str,
        messages: Sequence[Message],
        number: int,
        delay: float,
    ) -> Completion:
        address, port = route.server
        attrs: Attrs = {
            c.PROVIDER_NAME: route.provider,
            c.SERVER_ADDRESS: address,
            c.SERVER_PORT: port,
            c.ATTEMPT_NUMBER: number,
            c.ATTEMPT_DELAY: delay,
        }
        counted: Attrs = {
            c.PROVIDER_NAME: route.provider,
            c.REQUEST_MODEL: model,
        }
        with self._tracer.start_as_current_span(
            f"attempt {route.provider}",
            kind=SpanKind.INTERNAL,
            attributes=attrs,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                result = await self._adapters[route].chat(
                    model, messages
                )
            except ProviderError as err:
                failed: Attrs = {
                    c.ERROR_TYPE: err.error_type.value,
                    c.ATTEMPT_RETRYABLE: err.retryable,
                }
                if err.status is not None:
                    failed[c.HTTP_STATUS] = err.status
                if err.retry_after is not None:
                    failed[c.ATTEMPT_RETRY_AFTER] = err.retry_after
                span.set_attributes(failed)
                span.set_status(Status(StatusCode.ERROR))
                counted[c.ERROR_TYPE] = err.error_type.value
                self._attempts.add(1, counted)
                raise
            span.set_attribute(c.HTTP_STATUS, result.status)
            self._attempts.add(1, counted)
            return result

    def _end(
        self,
        span: Span,
        base: Attrs,
        start: float,
        attempts: int,
        *,
        result: Completion | None = None,
        err: ProviderError | None = None,
    ) -> None:
        span.set_attribute(c.ATTEMPT_COUNT, attempts)
        used = PROMPT.get()
        if used is not None:
            span.set_attributes(
                {c.PROMPT_NAME: used[0], c.PROMPT_VERSION: used[1]}
            )
        measured = dict(base)
        if result is not None:
            done: Attrs = {
                c.RESPONSE_MODEL: result.response_model,
                c.RESPONSE_ID: result.response_id,
                c.FINISH_REASONS: list(result.finish_reasons),
            }
            if result.input_tokens is not None:
                done[c.INPUT_TOKENS] = result.input_tokens
            if result.output_tokens is not None:
                done[c.OUTPUT_TOKENS] = result.output_tokens
            span.set_attributes(done)
            measured[c.RESPONSE_MODEL] = result.response_model
            self._check_pin(span, base, result.response_model)
        if err is not None:
            span.set_attribute(c.ERROR_TYPE, err.error_type.value)
            span.set_status(Status(StatusCode.ERROR))
            measured[c.ERROR_TYPE] = err.error_type.value
        self._duration.record(time.perf_counter() - start, measured)

    async def stream(
        self,
        model: str,
        messages: Sequence[Message],
        prompt: tuple[str, str] | None = None,
        result: StreamResult | None = None,
    ) -> AsyncGenerator[str]:
        """Stream an answer (Chapter 8). The request span lives as
        long as the stream. Until a chunk reaches the caller, any
        failure, a broken stream included, is retried as for chat;
        after that nothing is retried, and a failure ends the stream
        as stream_interrupted."""
        route = self._routes[model]
        address, port = route.server
        base: Attrs = {
            c.OPERATION_NAME: c.CHAT,
            c.PROVIDER_NAME: route.provider,
            c.REQUEST_MODEL: model,
            c.SERVER_ADDRESS: address,
            c.SERVER_PORT: port,
        }
        done = result if result is not None else StreamResult()
        clock = StreamClock(time.perf_counter())
        span = self._tracer.start_span(
            f"{c.CHAT} {model}", kind=SpanKind.CLIENT, attributes=base
        )
        if prompt is not None:
            span.set_attributes(
                {
                    c.PROMPT_NAME: prompt[0],
                    c.PROMPT_VERSION: prompt[1],
                }
            )
        parent = trace.set_span_in_context(span)
        measured = dict(base)
        attempt, delay = 0, 0.0
        tries: Span | None = None
        reply: AsyncGenerator[Chunk] | None = None
        try:
            while True:
                attempt += 1
                tries = self._open(route, parent, attempt, delay)
                reply = self._adapters[route].stream(model, messages)
                failed: ProviderError | None = None
                finished = False
                while True:
                    try:  # attached to read, never across a yield
                        with trace.use_span(tries, end_on_exit=False):
                            chunk = await anext(reply)
                    except StopAsyncIteration:
                        break
                    except ProviderError as err:
                        failed = err
                        break
                    finished = (
                        finished or chunk.finish_reason is not None
                    )
                    if not chunk.text:
                        continue
                    if clock.first is None:
                        done.response_model = chunk.model
                        measured[c.RESPONSE_MODEL] = chunk.model
                        self._check_pin(span, base, chunk.model)
                    gap = clock.chunk(time.perf_counter())
                    if gap is None:
                        self._ttfc.record(
                            clock.to_first or 0.0, measured
                        )
                    else:
                        self._tpoc.record(gap, measured)
                    yield chunk.text
                if failed is None and not finished:
                    failed = ProviderError(
                        ErrorType.STREAM_INTERRUPTED
                    )
                await reply.aclose()
                reply = None
                if failed is None:
                    self._close(tries, model, route, None, False)
                    tries = None
                    return
                delivered = clock.first is not None
                judged = failed if delivered else _undelivered(failed)
                self._close(
                    tries, model, route, failed, judged.retryable
                )
                tries = None
                wait = None
                if not delivered:
                    wait = self._policy.next_delay(
                        attempt, judged, self._jitter()
                    )
                if wait is None:
                    done.error = failed
                    raise failed
                delay = wait
                await self._sleep(delay)
        except (GeneratorExit, asyncio.CancelledError):
            done.cancelled = True
            raise
        finally:
            if reply is not None:  # stop the provider generating
                closing = asyncio.create_task(_aclose(reply))
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.shield(closing)
            if tries is not None:  # the caller left mid-attempt
                tries.set_attribute(c.STREAM_CANCELLED, True)
                self._attempts.add(
                    1,
                    {
                        c.PROVIDER_NAME: route.provider,
                        c.REQUEST_MODEL: model,
                    },
                )
                tries.end()
            self._end_stream(span, measured, clock, attempt, done)

    def _open(
        self, route: Route, parent: Context, number: int, delay: float
    ) -> Span:
        address, port = route.server
        return self._tracer.start_span(
            f"attempt {route.provider}",
            context=parent,
            kind=SpanKind.INTERNAL,
            attributes={
                c.PROVIDER_NAME: route.provider,
                c.SERVER_ADDRESS: address,
                c.SERVER_PORT: port,
                c.ATTEMPT_NUMBER: number,
                c.ATTEMPT_DELAY: delay,
            },
        )

    def _close(
        self,
        span: Span,
        model: str,
        route: Route,
        err: ProviderError | None,
        retryable: bool,
    ) -> None:
        counted: Attrs = {
            c.PROVIDER_NAME: route.provider,
            c.REQUEST_MODEL: model,
        }
        if err is not None:
            span.set_attributes(
                {
                    c.ERROR_TYPE: err.error_type.value,
                    c.ATTEMPT_RETRYABLE: retryable,
                }
            )
            span.set_status(Status(StatusCode.ERROR))
            counted[c.ERROR_TYPE] = err.error_type.value
        self._attempts.add(1, counted)
        span.end()

    def _end_stream(
        self,
        span: Span,
        measured: Attrs,
        clock: StreamClock,
        attempts: int,
        done: StreamResult,
    ) -> None:
        now = time.perf_counter()
        done.chunks = clock.chunks
        done.first_chunk_s = clock.to_first
        span.set_attributes(
            {c.ATTEMPT_COUNT: attempts, c.STREAM_CHUNKS: clock.chunks}
        )
        if clock.to_first is not None:  # the trace's own wait
            span.set_attribute(
                c.RESPONSE_TIME_TO_FIRST_CHUNK, clock.to_first
            )
        if c.RESPONSE_MODEL in measured:
            span.set_attribute(
                c.RESPONSE_MODEL, measured[c.RESPONSE_MODEL]
            )
        if done.cancelled:
            # The caller went away: not a provider error, and not a
            # completed operation, so no duration is recorded.
            span.set_attribute(c.STREAM_CANCELLED, True)
            span.end()
            return
        if done.error is not None:
            span.set_attribute(
                c.ERROR_TYPE, done.error.error_type.value
            )
            span.set_status(Status(StatusCode.ERROR))
            measured = {
                **measured,
                c.ERROR_TYPE: done.error.error_type.value,
            }
        done.duration_s = clock.total(now)
        self._duration.record(done.duration_s, measured)
        span.end()

    def _check_pin(self, span: Span, base: Attrs, got: str) -> None:
        requested = str(base[c.REQUEST_MODEL])
        pin = self._pinned.get(requested)
        if pin is None:
            return
        span.set_attribute(c.MODEL_MISMATCH, got != pin)
        if got != pin:
            self._mismatches.add(
                1,
                {
                    c.PROVIDER_NAME: base[c.PROVIDER_NAME],
                    c.REQUEST_MODEL: requested,
                    c.RESPONSE_MODEL: got,
                },
            )

    async def aclose(self) -> None:
        for adapter in self._adapters.values():
            await adapter.aclose()
