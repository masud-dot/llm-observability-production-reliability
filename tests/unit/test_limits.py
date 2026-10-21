"""Per-tenant consumption limits (Chapter 11)."""

import asyncio
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from services.mock_llm.server import running_provider
from wrenholt.api.app import Settings, create_app
from wrenholt.gateway import (
    SPEND,
    Gateway,
    Ledger,
    LimitExceeded,
    Message,
    Route,
    Spend,
    load_prices,
)
from wrenholt.telemetry import conventions as c


class Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_the_ledger_refuses_at_the_limit_until_the_hour_turns() -> (
    None
):
    clock = Clock(10 * 3600 + 1200)  # 20 minutes into an hour
    ledger = Ledger({"wrenholt": Decimal("0.0010")}, clock)
    ledger.admit("wrenholt")
    ledger.charge("wrenholt", Decimal("0.0006"))
    ledger.admit("wrenholt")  # under the limit: admitted
    ledger.charge("wrenholt", Decimal("0.0006"))  # and ends over it
    with pytest.raises(LimitExceeded) as refused:
        ledger.admit("wrenholt")
    assert refused.value.retry_after == 2400  # to the next hour
    clock.now = 11 * 3600
    ledger.admit("wrenholt")
    assert ledger.spent("wrenholt") == 0


def test_a_tenant_without_a_limit_is_refused() -> None:
    ledger = Ledger({"wrenholt": Decimal("60")})
    with pytest.raises(LimitExceeded):
        ledger.admit("someone-else")


def run_refused(
    tenant: str,
) -> tuple[list[ReadableSpan], int, dict[str, Any]]:
    spans = InMemorySpanExporter()
    tracing = TracerProvider()
    tracing.add_span_processor(SimpleSpanProcessor(spans))
    reader = InMemoryMetricReader()
    meters = MeterProvider(metric_readers=[reader])

    async def go(url: str) -> None:
        gw = Gateway(
            {"mock-a-fast": Route("wrenholt.mock_a", url, "x")},
            tracer_provider=tracing,
            meter_provider=meters,
            prices=load_prices(),
            ledger=Ledger({"wrenholt": Decimal("0")}),
        )
        SPEND.set(Spend(tenant))
        try:
            with pytest.raises(LimitExceeded):
                await gw.chat("mock-a-fast", [Message("user", "Hi")])
        finally:
            await gw.aclose()

    with running_provider() as mock:
        asyncio.run(go(mock.base_url))
        reached = len(mock.log)
    data = reader.get_metrics_data()
    points = {
        m.name: [
            (dict(p.attributes or {}), p) for p in m.data.data_points
        ]
        for r in (data.resource_metrics if data else [])
        for s in r.scope_metrics
        for m in s.metrics
    }
    return list(spans.get_finished_spans()), reached, points


def test_a_refused_call_never_reaches_the_provider() -> None:
    spans, reached, points = run_refused("wrenholt")
    assert reached == 0
    (request,) = spans  # the CLIENT span, and no attempt under it
    attrs = request.attributes or {}
    assert attrs[c.ERROR_TYPE] == c.CONSUMPTION_LIMIT
    assert attrs[c.TENANT] == "wrenholt"
    (limited,) = points[c.LIMITED]
    assert limited[0] == {c.TENANT: "wrenholt"}
    assert limited[1].value == 1
    assert c.OPERATION_DURATION not in points  # nothing was operated
    (limit,) = points[c.SPEND_LIMIT]
    assert limit[0] == {c.TENANT: "wrenholt"} and limit[1].value == 0


def test_an_unknown_tenant_is_counted_as_other() -> None:
    _, _, points = run_refused("not-configured")
    (limited,) = points[c.LIMITED]
    assert limited[0] == {c.TENANT: c.OTHER}


def test_the_api_answers_429_with_retry_after() -> None:
    app = create_app(Settings(spend_per_hour="0"))
    with TestClient(app) as client:
        reply = client.post(
            "/chat", json={"message": "Return policy?"}
        )
    assert reply.status_code == 429
    assert 0 < int(reply.headers["retry-after"]) <= 3600
    assert reply.json() == {"detail": "Linnet cannot answer now."}
