"""Deterministic OpenAI-compatible mock provider (SIMULATED).

Serves POST /v1/chat/completions for the models of one mock
provider and records every request it receives. The record lets a
reader compare what the provider saw with what the client's
telemetry reports.
"""

import os
import threading
import time
from dataclasses import asdict, dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

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
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[Message]
    stream: bool = False


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


def completion(req: ChatRequest, arrival: int) -> dict[str, object]:
    text = pick_answer(req.messages[-1].content)
    prompt = sum(count_tokens(m.content) for m in req.messages)
    output = count_tokens(text)
    message = {"role": "assistant", "content": text}
    return {
        "id": f"chatcmpl-mock-{arrival:06d}",
        "object": "chat.completion",
        "created": 1790000000,
        "model": MODELS[req.model],
        "choices": [
            {"index": 0, "finish_reason": "stop", "message": message}
        ],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": output,
            "total_tokens": prompt + output,
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
