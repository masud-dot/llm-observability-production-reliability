"""Context and yield (Chapter 8). A generator runs in whichever
context reads it: the first chunk is read in the request handler's
task and the rest in the response task, as Starlette does."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from services.mock_llm.server import running_provider
from services.mock_llm.streaming import Schedule
from wrenholt.gateway import Gateway, Message, Route
from wrenholt.gateway.context import PROMPT, prompt

QUESTION = [Message("user", "When will my refund arrive?")]
FAST: dict[str, Any] = {"first_s": 0.05, "gap_s": 0.02}


def tracing() -> tuple[TracerProvider, InMemorySpanExporter]:
    spans = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(spans))
    return provider, spans


async def read_in_two_tasks(
    chunks: AsyncGenerator[str],
) -> trace.Span:
    """The first chunk here, the rest in another task; returns the
    span current here after the first chunk."""
    await anext(chunks)
    seen = trace.get_current_span()

    async def rest() -> None:
        async for _ in chunks:
            pass

    await asyncio.create_task(rest())
    return seen


def test_a_span_held_across_a_yield_leaks_and_cannot_detach(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider, _ = tracing()
    tracer = provider.get_tracer("test")
    made: list[trace.Span] = []

    async def held() -> AsyncGenerator[str]:
        with tracer.start_as_current_span("chat") as span:  # mistake
            made.append(span)
            yield "Refunds "
            yield "reach your card."

    with caplog.at_level(logging.ERROR, "opentelemetry.context"):
        seen = asyncio.run(read_in_two_tasks(held()))
    assert seen is made[0]  # current in the caller's code
    assert "Failed to detach context" in caplog.text


def test_a_generator_leaks_its_context_variable() -> None:
    async def held() -> AsyncGenerator[str]:
        with prompt("support", "v3"):  # the same mistake
            yield "Refunds "
            yield "reach your card."

    async def go() -> tuple[str, str] | None:
        chunks = held()
        await anext(chunks)
        seen = PROMPT.get()  # the caller's own context
        await chunks.aclose()
        return seen

    assert asyncio.run(go()) == ("support", "v3")


def test_the_gateway_holds_no_context_across_a_yield(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider, spans = tracing()
    tracer = provider.get_tracer("test")
    with running_provider(streaming=Schedule(**FAST)) as mock:
        route = Route("wrenholt.mock_a", mock.base_url, "x")

        async def go() -> tuple[trace.Span, trace.Span]:
            gw = Gateway(
                {"mock-a-fast": route}, tracer_provider=provider
            )
            with tracer.start_as_current_span("handler") as handler:
                chunks = gw.stream("mock-a-fast", QUESTION)
                seen = await read_in_two_tasks(chunks)
            await gw.aclose()
            return handler, seen

        with caplog.at_level(logging.ERROR, "opentelemetry.context"):
            handler, seen = asyncio.run(go())
    assert seen is handler  # nothing of the gateway's became current
    assert "Failed to detach context" not in caplog.text
    finished = spans.get_finished_spans()
    (request,) = [s for s in finished if s.name == "chat mock-a-fast"]
    (attempt,) = [s for s in finished if s.name.startswith("attempt")]
    assert request.parent and attempt.parent and request.context
    handler_id = handler.get_span_context().span_id
    assert request.parent.span_id == handler_id
    assert attempt.parent.span_id == request.context.span_id
