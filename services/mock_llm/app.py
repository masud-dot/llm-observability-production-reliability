"""Deterministic OpenAI-compatible mock provider (SIMULATED).

Serves POST /v1/chat/completions for the models of one mock
provider and records every request it receives. The record lets a
reader compare what the provider saw with what the client's
telemetry reports.
"""

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from services.mock_llm.decide import decide, from_notes
from services.mock_llm.faults import NO_FAULTS, FaultPlan

# Requested model -> model the response reports (dated snapshot).
# Provider A serves a fast and a large model; provider B is the
# fallback. A process serves one provider, chosen at start-up.
PROVIDER_MODELS = {
    "a": {
        "mock-a-fast": "mock-a-fast-2026-09",
        "mock-a-large": "mock-a-large-2026-09",
    },
    "b": {"mock-b-standard": "mock-b-standard-2026-09"},
}
MODELS = PROVIDER_MODELS[os.environ.get("MOCK_LLM_PROVIDER", "a")]

# Deterministic answers chosen by keyword; the first match wins.
ANSWERS = (
    ("refund", "Refunds reach your card within five working days."),
    ("return", "Most items can be returned within 30 days."),
    ("order", "Order status is shown under My orders."),
)
DEFAULT_ANSWER = "I can help with orders, returns and refunds."

RETRY_COUNT_HEADER = "x-stainless-retry-count"
Reply = tuple[int, dict[str, object], dict[str, str]]


class Message(BaseModel):
    role: str
    content: str | None = None
    # Chapter 9: tool calls and the tool turns that answer them.
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


class ChatRequest(BaseModel):
    model: str
    messages: list[Message]
    stream: bool = False
    tools: list[dict[str, Any]] | None = None  # Chapter 9
    tool_choice: Any = None
    # Chapter 11: the output cap, by its current name or its old one
    max_completion_tokens: int | None = None
    max_tokens: int | None = None


@dataclass(frozen=True)
class Received:
    """One request as the provider saw it."""

    arrival: int
    at_ns: int
    status: int
    retry_count: str | None


class ProviderLog:
    """Requests received; safe to read from another thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: list[Received] = []

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def add(self, item: Received) -> None:
        with self._lock:
            self._items.append(item)

    def items(self) -> list[Received]:
        with self._lock:
            return list(self._items)


def error_body(kind: str, message: str) -> dict[str, object]:
    return {"error": {"type": kind, "message": message}}


def pick_answer(question: str) -> str:
    lowered = question.lower()
    for keyword, text in ANSWERS:
        if keyword in lowered:
            return text
    return DEFAULT_ANSWER


def count_tokens(text: str) -> int:
    """Whitespace word count: a SIMULATED tokenizer."""
    return len(text.split())


def reply_to(req: ChatRequest, arrival: int) -> dict[str, Any]:
    """The assistant message: tool calls when tools are offered
    (Chapter 9), else an answer, from Linnet's notes if any."""
    if req.tools:
        calls = decide(req.messages, arrival)
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": calls,
        }
    question = req.messages[-1].content or ""
    notes = [m.content or "" for m in req.messages[1:-1]]
    text = from_notes(question, notes) or pick_answer(question)
    return {"role": "assistant", "content": text}


# Chapter 11 (SIMULATED). Asked in its system prompt to answer
# thoroughly, the mock says the same thing at greater length.
THOROUGH = "thoroughly"
PADDING = (
    "To be thorough, here is the same point again in more detail, "
    "with the background that applies to every order."
)


class PrefixCache:
    """A provider-managed prompt cache, reduced to its idea: once a
    model has seen a system message, later requests that start with
    it read those tokens from the cache. Real providers cache long
    prefixes in blocks, and only above a minimum length."""

    def __init__(self) -> None:
        self._seen: set[tuple[str, str]] = set()
        self._lock = threading.Lock()

    def read(self, req: ChatRequest) -> int:
        first = req.messages[0] if req.messages else None
        if first is None or first.role != "system":
            return 0
        key = (req.model, first.content or "")
        with self._lock:
            hit = key in self._seen
            self._seen.add(key)
        return count_tokens(key[1]) if hit else 0

    def clear(self) -> None:
        with self._lock:
            self._seen.clear()


PREFIX_CACHE = PrefixCache()


def thorough(req: ChatRequest) -> bool:
    return any(
        THOROUGH in (m.content or "")
        for m in req.messages
        if m.role == "system"
    )


def input_tokens(req: ChatRequest) -> int:
    """Every message, and the tools offered: schemas are input."""
    text = sum(count_tokens(m.content or "") for m in req.messages)
    calls = sum(
        count_tokens(json.dumps(c)) for m in req.messages
        for c in m.tool_calls or ()
    )  # fmt: skip
    offered = count_tokens(json.dumps(req.tools)) if req.tools else 0
    return text + calls + offered


def completion(req: ChatRequest, arrival: int) -> dict[str, object]:
    message = reply_to(req, arrival)
    finish = "tool_calls" if message.get("tool_calls") else "stop"
    text = message["content"]
    if text and thorough(req):
        text = " ".join([text, *[PADDING] * 4])
    words = (text or "").split()
    cap = req.max_completion_tokens or req.max_tokens
    if cap is not None and len(words) > cap:
        text, finish = " ".join(words[:cap]), "length"
    if text is not None:
        message = {**message, "content": text}
    prompt = input_tokens(req)
    output = count_tokens(text or "") + sum(
        count_tokens(json.dumps(c["function"]))
        for c in message.get("tool_calls") or ()
    )
    cached = PREFIX_CACHE.read(req)
    return {
        "id": f"chatcmpl-mock-{arrival:06d}",
        "object": "chat.completion",
        "created": 1790000000,
        "model": MODELS[req.model],
        "choices": [
            {"index": 0, "finish_reason": finish, "message": message}
        ],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": output,
            "total_tokens": prompt + output,
            "prompt_tokens_details": {"cached_tokens": cached},
        },
    }


def respond(plan: FaultPlan, req: ChatRequest, arrival: int) -> Reply:
    if plan.rate_limits(arrival):
        wait = {"retry-after": str(plan.retry_after_s)}
        body = error_body("rate_limit_error", "Rate limit reached.")
        return 429, body, wait
    if req.model not in MODELS:
        body = error_body("invalid_request_error", "Unknown model.")
        return 404, body, {}
    if req.stream:
        body = error_body("invalid_request_error", "No streaming.")
        return 400, body, {}
    return 200, completion(req, arrival), {}


def create_app(
    plan: FaultPlan = NO_FAULTS, log: ProviderLog | None = None
) -> FastAPI:
    record = log if log is not None else ProviderLog()
    app = FastAPI(title="mock-llm")

    @app.post("/v1/chat/completions")
    async def chat(
        req: ChatRequest, request: Request
    ) -> JSONResponse:
        at_ns = time.time_ns()
        # No await between counting and recording, so arrival
        # order is exact on the event loop.
        arrival = len(record)
        status, body, headers = respond(plan, req, arrival)
        retry_count = request.headers.get(RETRY_COUNT_HEADER)
        record.add(Received(arrival, at_ns, status, retry_count))
        return JSONResponse(body, status_code=status, headers=headers)

    @app.get("/mock/requests")
    async def received() -> list[dict[str, object]]:
        return [asdict(item) for item in record.items()]

    return app
