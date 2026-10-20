"""Run the gateway once per scenario and record every name."""

import asyncio
from contextlib import aclosing
from decimal import Decimal
from typing import Any

import pytest
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
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
from opentelemetry.trace import SpanContext, TraceFlags

from services.mock_llm.faults import FS01_HIDDEN_RETRY_STORM
from services.mock_llm.model_swap import FS11_SWAP
from services.mock_llm.server import running_provider
from services.mock_llm.streaming import Schedule
from services.orders.app import create_app as orders_app
from services.orders.store import OrderStore, generate_orders
from services.serving import serve
from wrenholt.evaluation.emitter import ResultEmitter
from wrenholt.evaluation.evaluators import Sample, standard
from wrenholt.gateway import (
    SPEND,
    Gateway,
    Ledger,
    LimitExceeded,
    Message,
    ProviderError,
    Route,
    Spend,
    load_prices,
)
from wrenholt.gateway.context import prompt
from wrenholt.gateway.deadlines import deadline
from wrenholt.gateway.fallback import FallbackGateway
from wrenholt.gateway.guarded import GuardedGateway
from wrenholt.gateway.retry import GuardedPolicy, RetryBudget
from wrenholt.guardrail import Guardrail
from wrenholt.orchestrator.linnet import Linnet
from wrenholt.privacy.pseudonym import keys_from_env
from wrenholt.privacy.redact import Redactor
from wrenholt.rag.embed import EMBEDDERS
from wrenholt.rag.index import index_as_of
from wrenholt.rag.retriever import Retriever
from wrenholt.slo.recorder import SliRecorder
from wrenholt.telemetry import conventions as c
from wrenholt.tools.orders import OrdersClient

Metric = tuple[str, str, str, set[str]]
# Chapter 11: every gateway meters, prices, caps and limits.
PRICED: dict[str, Any] = {
    "prices": load_prices(),
    "max_tokens": {"mock-a-fast": 512},
}


def ledger(limit: str = "100") -> Ledger:
    return Ledger({"wrenholt": Decimal(limit)})


async def no_wait(_: float) -> None:
    return None


# Appendix A: the span and event names the scenarios emit.
SEEN: dict[str, set[str]] = {}


@pytest.fixture(scope="session")
def seen(
    emitted: tuple[set[str], list[Metric]],
) -> dict[str, set[str]]:
    return SEEN


@pytest.fixture(scope="session")
def emitted() -> tuple[set[str], list[Metric]]:
    """Attribute keys on Wrenholt's own spans (and registered ones on
    its metrics), and each metric's name, instrument, unit and
    attribute keys, over FS-01, FS-18 and FS-11, with a prompt and
    model pins in place (Chapter 6),
    two streamed answers, one left early (Chapter 8), Linnet
    answering a policy question and a refund (Chapter 9), a call
    refused at the spend limit (Chapter 11), the API's SLI events
    and a guardrail refusal (Chapter 12), one answer's evaluation
    results, as events and counts (Chapter 13), and a guarded call
    whose breaker opens under a deadline (Chapter 16), and one that
    falls back to provider B (Chapter 17)."""
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
            ledger=ledger(),
            **PRICED,
        )
        try:
            with prompt("linnet.support", "1"):
                await gw.chat("mock-a-fast", [Message("user", "Hi")])
        except ProviderError:
            pass
        finally:
            await gw.aclose()

    async def refused(route: Route) -> None:
        gw = Gateway(
            {"mock-a-fast": route},
            tracer_provider=tracing,
            meter_provider=meters,
            ledger=ledger("0"),
            **PRICED,
        )
        try:
            await gw.chat("mock-a-fast", [Message("user", "Hi")])
        except LimitExceeded:
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
    with running_provider() as mock:
        asyncio.run(
            refused(Route("wrenholt.mock_a", mock.base_url, "x"))
        )

    async def guarded() -> None:
        """Chapter 16: nothing listens on port 9, the first failure
        opens the breaker, and the retry is refused."""
        route = Route("wrenholt.mock_a", "http://127.0.0.1:9/v1", "x")
        gw = GuardedGateway(
            {"mock-a-fast": route},
            GuardedPolicy(RetryBudget()),
            tracer_provider=tracing,
            meter_provider=meters,
            sleep=no_wait,
            failures=1,
            **PRICED,
        )
        try:
            with deadline(10.0):
                await gw.chat("mock-a-fast", [Message("user", "Hi")])
        except ProviderError:
            pass
        finally:
            await gw.aclose()

    asyncio.run(guarded())

    async def fell_back(b: Route) -> None:
        """Chapter 17: nothing listens for A, so B answers."""
        a = Route("wrenholt.mock_a", "http://127.0.0.1:9/v1", "x")
        gw = FallbackGateway(
            {"mock-a-fast": a, "mock-b-standard": b},
            GuardedPolicy(RetryBudget()),
            tracer_provider=tracing,
            meter_provider=meters,
            sleep=no_wait,
            chains={"mock-a-fast": ["mock-b-standard"]},
            **PRICED,
        )
        tracer = tracing.get_tracer("wrenholt.drift")
        try:
            with tracer.start_as_current_span("answer"):
                await gw.chat("mock-a-fast", [Message("user", "Hi")])
        finally:
            await gw.aclose()

    with running_provider(provider="b") as mock:
        asyncio.run(
            fell_back(Route("wrenholt.mock_b", mock.base_url, "x"))
        )

    async def stream(route: Route, leave_after: int) -> None:
        gw = Gateway(
            {"mock-a-fast": route},
            tracer_provider=tracing,
            meter_provider=meters,
            sleep=no_wait,
            ledger=ledger(),
            **PRICED,
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

    async def agent(provider: str, orders_url: str) -> None:
        route = Route("wrenholt.mock_a", provider, "x")
        gw = Gateway(
            {"mock-a-fast": route},
            tracer_provider=tracing,
            meter_provider=meters,
            sleep=no_wait,
            ledger=ledger(),
            **PRICED,
        )
        embedder = EMBEDDERS["wrenholt-embed-1"]
        retriever = Retriever(
            index_as_of("2026-09-30", embedder),
            embedder,
            tracer_provider=tracing,
            meter_provider=meters,
        )
        linnet = Linnet(
            retriever, tracer_provider=tracing, meter_provider=meters
        )
        orders = OrdersClient(orders_url)
        try:
            for question in (
                "How long do I have to return an item?",
                "Please refund £5.00 on order WG-100006.",
            ):
                SPEND.set(Spend("wrenholt"))  # as the API does
                await linnet.answer(
                    gw, "mock-a-fast", question, orders
                )
        finally:
            await orders.aclose()
            await gw.aclose()

    store = OrderStore(generate_orders())
    with running_provider() as mock, serve(orders_app(store)) as url:
        asyncio.run(agent(mock.base_url, url))
    slis = SliRecorder(meter_provider=meters)
    slis.start()
    slis.first_chunk("critical_action", 0.4)
    refund = "Please refund £5.00 on order WG-100006."
    slis.event(
        "not_refused", Guardrail("2", tracing).screen(refund) is None
    )
    logs = InMemoryLogRecordExporter()  # type: ignore[no-untyped-call]
    events = LoggerProvider()
    events.add_log_record_processor(SimpleLogRecordProcessor(logs))
    results, judges = ResultEmitter(events, meters), standard()
    results.start(judges, "1", "index-1")
    sample = Sample(
        "How long do I have to return an item?",
        "Most items can be returned within 30 days.",
        ("Most items can be returned within 30 days of delivery.",),
        "1",
        "index-1",
    )
    span = SpanContext(
        1, 2, is_remote=False, trace_flags=TraceFlags(1)
    )
    for judge in judges:
        verdict = judge.evaluate(sample)
        if verdict is not None:
            linked = (
                span,
                "chatcmpl-mock-000001",
                "mock-a-fast-2026-09",
            )
            results.emit(judge, verdict, sample, *linked)
    attrs = {
        key
        for span in spans.get_finished_spans()
        if span.instrumentation_scope
        and span.instrumentation_scope.name.startswith("wrenholt.")
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
                    else "gauge"
                    if type(m.data).__name__ == "Gauge"
                    else "counter"
                )
                keys = {
                    k for p in points for k in (p.attributes or {})
                }
                metrics.append((m.name, kind, m.unit or "", keys))
    # Chapter 11: a registered name may only ever be a metric's, as
    # gen_ai.token.modality is.
    registered = {n.name for n in c.REGISTRY}
    attrs |= {k for metric in metrics for k in metric[3]} & registered
    # Chapter 16: so are those of the gateway's span events.
    attrs |= {
        key
        for span in spans.get_finished_spans()
        for event in span.events
        if event.name
        in (c.RETRY_EVENT, c.BREAKER_EVENT, c.FALLBACK_EVENT)
        for key in (event.attributes or {})
    }
    # Chapter 13: an event's attributes are emitted names too.
    attrs |= {
        k
        for r in logs.get_finished_logs()
        for k in (r.log_record.attributes or {})
    }
    finished = spans.get_finished_spans()
    SEEN["spans"] = {s.name for s in finished}
    SEEN["events"] = {e.name for s in finished for e in s.events} | {
        str(r.log_record.event_name)
        for r in logs.get_finished_logs()
        if r.log_record.event_name
    }
    return attrs, metrics
