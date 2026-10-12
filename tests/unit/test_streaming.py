"""The gateway's streams on deterministic chunk schedules: timers,
retries before the first chunk, none after it, and departures."""

import asyncio
from contextlib import aclosing
from dataclasses import dataclass
from typing import Any

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from services.mock_llm.server import running_provider
from services.mock_llm.streaming import Schedule, Sent
from wrenholt.gateway import (
    Gateway,
    Message,
    ProviderError,
    Route,
    StreamResult,
)
from wrenholt.labs.fs02_lab import points
from wrenholt.telemetry import conventions as c

QUESTION = [Message("user", "When will my refund arrive?")]
ANSWER = "Refunds reach your card within five working days."
FAST: dict[str, Any] = {"first_s": 0.05, "gap_s": 0.02}


@dataclass
class Run:
    text: list[str]
    result: StreamResult
    request: Any
    attempts: list[Any]
    reader: InMemoryMetricReader
    sent: list[Sent]


async def no_wait(_: float) -> None:
    return None


def stream(schedule: Schedule, leave_after: int = 0) -> Run:
    spans = InMemorySpanExporter()
    tracing = TracerProvider()
    tracing.add_span_processor(SimpleSpanProcessor(spans))
    reader = InMemoryMetricReader()
    meters = MeterProvider(metric_readers=[reader])
    sent: list[Sent] = []
    text: list[str] = []
    done = StreamResult()
    with running_provider(streaming=schedule, sent=sent) as mock:
        route = Route("wrenholt.mock_a", mock.base_url, "x")

        async def go() -> None:
            gw = Gateway(
                {"mock-a-fast": route},
                tracer_provider=tracing,
                meter_provider=meters,
                sleep=no_wait,
            )
            chunks = gw.stream("mock-a-fast", QUESTION, None, done)
            try:
                async with aclosing(chunks) as answer:
                    async for piece in answer:
                        text.append(piece)
                        if len(text) == leave_after:
                            break
            except ProviderError:
                pass
            await asyncio.sleep(0.2)  # the provider notices
            await gw.aclose()

        asyncio.run(go())
    finished = spans.get_finished_spans()
    (request,) = [s for s in finished if s.name == "chat mock-a-fast"]
    attempts = [s for s in finished if s.name.startswith("attempt")]
    return Run(text, done, request, attempts, reader, sent)


def test_a_steady_stream_records_both_timers() -> None:
    run = stream(Schedule(**FAST))
    assert "".join(run.text) == ANSWER
    assert (run.result.chunks, run.result.error) == (8, None)
    assert run.result.first_chunk_s is not None
    assert run.result.first_chunk_s >= 0.05
    (first,) = points(run.reader, c.TIME_TO_FIRST_CHUNK)
    (gaps,) = points(run.reader, c.TIME_PER_OUTPUT_CHUNK)
    assert (first.count, gaps.count) == (1, 7)
    attributes = run.request.attributes
    assert attributes[c.STREAM_CHUNKS] == 8
    # The trace carries its own wait, the metric's value.
    waited = attributes[c.RESPONSE_TIME_TO_FIRST_CHUNK]
    assert waited == run.result.first_chunk_s == first.sum


def test_a_whole_answer_records_no_stream_timers() -> None:
    reader = InMemoryMetricReader()
    with running_provider(streaming=Schedule(**FAST)) as mock:
        route = Route("wrenholt.mock_a", mock.base_url, "x")

        async def go() -> None:
            meters = MeterProvider(metric_readers=[reader])
            gw = Gateway(
                {"mock-a-fast": route}, meter_provider=meters
            )
            await gw.chat("mock-a-fast", QUESTION)
            await gw.aclose()

        asyncio.run(go())
    assert points(reader, c.TIME_TO_FIRST_CHUNK) == []
    assert len(points(reader, c.OPERATION_DURATION)) == 1


def test_a_slow_first_chunk_moves_only_the_first_timer() -> None:
    slow = stream(Schedule(first_s=0.4, gap_s=0.02))
    assert slow.result.first_chunk_s is not None
    assert slow.result.first_chunk_s >= 0.4
    (gaps,) = points(slow.reader, c.TIME_PER_OUTPUT_CHUNK)
    assert gaps.sum / gaps.count < 0.1


@pytest.mark.parametrize(
    "fault", [{"cut_after": 3}, {"error_after": 3}]
)
def test_after_the_first_chunk_nothing_is_retried(
    fault: dict[str, int],
) -> None:
    run = stream(Schedule(**FAST, **fault))
    assert "".join(run.text) == "Refunds reach your "  # stays sent
    assert run.result.error is not None
    assert run.result.error.error_type == "stream_interrupted"
    assert len(run.attempts) == 1
    assert (
        run.request.attributes[c.ERROR_TYPE] == "stream_interrupted"
    )
    assert run.request.attributes[c.STREAM_CHUNKS] == 3


def test_a_cut_before_the_first_chunk_is_retried() -> None:
    run = stream(Schedule(**FAST, cut_after=0, faulty=1))
    assert (run.result.chunks, run.result.error) == (8, None)
    first, second = run.attempts
    assert first.attributes[c.ERROR_TYPE] == "stream_interrupted"
    assert first.attributes[c.ATTEMPT_RETRYABLE] is True
    assert c.ERROR_TYPE not in (second.attributes or {})


def test_a_stream_that_never_starts_gives_up_after_three() -> None:
    run = stream(Schedule(**FAST, error_after=0))
    assert len(run.attempts) == 3
    assert run.result.chunks == 0
    assert points(run.reader, c.TIME_TO_FIRST_CHUNK) == []
    attributes = run.request.attributes or {}
    assert c.RESPONSE_TIME_TO_FIRST_CHUNK not in attributes


def test_a_departure_cancels_and_stops_the_provider() -> None:
    run = stream(Schedule(first_s=0.05, gap_s=0.1), leave_after=2)
    assert run.result.cancelled and run.result.error is None
    attributes = run.request.attributes
    assert attributes[c.STREAM_CANCELLED] is True
    assert c.ERROR_TYPE not in attributes
    assert attributes[c.RESPONSE_TIME_TO_FIRST_CHUNK] >= 0.05
    assert points(run.reader, c.OPERATION_DURATION) == []
    (sent,) = run.sent
    assert sent.outcome == "client_gone"
    assert sent.chunks < sent.planned
