"""Run the gateway once per scenario and record every name."""

import asyncio
from contextlib import aclosing
from typing import Any

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    HistogramDataPoint,
    InMemoryMetricReader,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from services.mock_llm.faults import FS01_HIDDEN_RETRY_STORM
from services.mock_llm.model_swap import FS11_SWAP
from services.mock_llm.server import running_provider
from services.mock_llm.streaming import Schedule
from wrenholt.gateway import Gateway, Message, ProviderError, Route
from wrenholt.gateway.context import prompt
from wrenholt.privacy.pseudonym import keys_from_env
from wrenholt.privacy.redact import Redactor

Metric = tuple[str, str, str, set[str]]


async def no_wait(_: float) -> None:
    return None


@pytest.fixture(scope="session")
def emitted() -> tuple[set[str], list[Metric]]:
    """Attribute keys on gateway spans, and each metric's name,
    instrument, unit and attribute keys, over FS-01, FS-18 and
    FS-11, with a prompt and model pins in place (Chapter 6), and
    two streamed answers, one left early (Chapter 8)."""
    spans = InMemorySpanExporter()
    tracing = TracerProvider()
    tracing.add_span_processor(SimpleSpanProcessor(spans))
    reader = InMemoryMetricReader()
    meters = MeterProvider(metric_readers=[reader])

    async def ask(route: Route) -> None:
        gw = Gateway(
            {"mock-a-fast": route},
            tracer_provider=tracing,
            meter_provider=meters,
            sleep=no_wait,
            pinned={"mock-a-fast": "mock-a-fast-2026-09"},
        )
        try:
            with prompt("linnet.support", "1"):
                await gw.chat("mock-a-fast", [Message("user", "Hi")])
        except ProviderError:
            pass
        finally:
            await gw.aclose()

    fs01 = running_provider(FS01_HIDDEN_RETRY_STORM)
    fs18 = running_provider(spend_cap=True)
    fs11 = running_provider(model_swap=FS11_SWAP)
    for scenario in (fs01, fs18, fs11):
        with scenario as mock:
            asyncio.run(
                ask(Route("wrenholt.mock_a", mock.base_url, "x"))
            )

    async def stream(route: Route, leave_after: int) -> None:
        gw = Gateway(
            {"mock-a-fast": route},
            tracer_provider=tracing,
            meter_provider=meters,
            sleep=no_wait,
        )
        used = ("linnet.support", "1")
        chunks = gw.stream(
            "mock-a-fast", [Message("user", "Hi")], used
        )
        async with aclosing(chunks) as answer:
            got = 0
            async for _ in answer:
                got += 1
                if got == leave_after:
                    break
        await gw.aclose()

    fast = Schedule(first_s=0.01, gap_s=0.01)
    with running_provider(streaming=fast) as mock:
        route = Route("wrenholt.mock_a", mock.base_url, "x")
        asyncio.run(stream(route, 0))  # 0: read to the end
        asyncio.run(stream(route, 2))
    # Chapter 7: one redaction, so the counter is emitted too.
    Redactor(keys_from_env(), meters).text("order WG-100006", "log")
    attrs = {
        key
        for span in spans.get_finished_spans()
        if span.instrumentation_scope
        and span.instrumentation_scope.name == "wrenholt.gateway"
        for key in (span.attributes or {})
    }
    metrics: list[Metric] = []
    data = reader.get_metrics_data()
    for resource in data.resource_metrics if data else []:
        for scope in resource.scope_metrics:
            for m in scope.metrics:
                points: list[Any] = list(m.data.data_points)
                kind = (
                    "histogram"
                    if isinstance(points[0], HistogramDataPoint)
                    else "counter"
                )
                keys = {
                    k for p in points for k in (p.attributes or {})
                }
                metrics.append((m.name, kind, m.unit or "", keys))
    return attrs, metrics
