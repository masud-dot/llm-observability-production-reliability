"""Tokens, prices and the cost meter (Chapter 11)."""

import asyncio
from contextlib import aclosing
from decimal import Decimal
from pathlib import Path

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from services.mock_llm.server import running_provider
from services.mock_llm.streaming import FS04_CUT, Schedule
from wrenholt.api import app as api
from wrenholt.api.app import Settings, routes
from wrenholt.gateway import (
    SPEND,
    Gateway,
    Message,
    ProviderError,
    Route,
    Spend,
    Usage,
    load_prices,
)
from wrenholt.gateway.cost import Attrs, CostMeter, Price, PriceTable
from wrenholt.gateway.cost import load_prices as load
from wrenholt.telemetry import conventions as c

FAST = load_prices().prices["mock-a-fast"]
LARGE = load_prices().prices["mock-a-large"]
FAST_STREAM = Schedule(first_s=0.01, gap_s=0.01)


def test_every_routed_model_has_a_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = load_prices()
    assert table.missing(routes(Settings())) == []
    assert table.version == "2026-10-01"
    # and the API refuses to start without one
    partial = PriceTable(table.version, {"mock-a-fast": FAST})
    monkeypatch.setattr(api, "load_prices", lambda: partial)
    with pytest.raises(
        ValueError, match="mock-a-large, mock-b-standard"
    ):
        api.create_app(Settings())


def test_one_policy_answer_by_hand() -> None:
    # Section 11.3: 86 input tokens, 13 of them cached, 8 output.
    usage = Usage(86, 8, 13)
    by_hand = (73 * Decimal("0.40") + 13 * Decimal("0.10")
               + 8 * Decimal("1.60")) / 1_000_000  # fmt: skip
    assert FAST.of(usage) == by_hand == Decimal("0.0000433")


def test_cached_tokens_are_input_at_the_cached_rate() -> None:
    saved = FAST.of(Usage(86, 8, 0)) - FAST.of(Usage(86, 8, 13))
    assert saved == 13 * (Decimal("0.40") - Decimal("0.10")) / 10**6
    assert FAST.of(Usage(86, 8)) == FAST.of(Usage(86, 8, 0))


def test_the_large_model_costs_five_times_as_much() -> None:
    usage = Usage(741, 33, 52)  # one refund answer's four calls
    assert FAST.of(usage) == Decimal("0.0003336")
    assert LARGE.of(usage) == 5 * FAST.of(usage)


def test_a_price_table_that_looks_wrong_stops_loading(
    tmp_path: Path,
) -> None:
    path = tmp_path / "prices.yaml"
    path.write_text(
        'version: "x"\ncurrency: USD\nmodels:\n  m:\n'
        '    input: "0.10"\n    cached_input: "0.40"\n'
        '    output: "1.00"\n'
    )
    with pytest.raises(ValueError, match="looks wrong"):
        load(path)
    path.write_text(path.read_text().replace("USD", "GBP"))
    with pytest.raises(ValueError, match="USD"):
        load(path)


class Run:
    def __init__(self) -> None:
        self.spans = InMemorySpanExporter()
        self.tracing = TracerProvider()
        self.tracing.add_span_processor(
            SimpleSpanProcessor(self.spans)
        )
        self.reader = InMemoryMetricReader()
        self.meters = MeterProvider(metric_readers=[self.reader])

    def gateway(self, url: str) -> Gateway:
        route = Route("wrenholt.mock_a", url, "sk-mock")
        return Gateway(
            {"mock-a-fast": route},
            tracer_provider=self.tracing,
            meter_provider=self.meters,
            prices=load_prices(),
            max_tokens={"mock-a-fast": 512},
        )

    def values(
        self, name: str
    ) -> list[tuple[dict[str, object], float]]:
        data = self.reader.get_metrics_data()
        return [
            (
                dict(p.attributes or {}),
                p.value if hasattr(p, "value") else p.sum,
            )
            for r in (data.resource_metrics if data else [])
            for s in r.scope_metrics
            for m in s.metrics
            if m.name == name
            for p in m.data.data_points
        ]


PROMPT = [
    Message("system", "You are Linnet. Answer briefly."),
    Message("user", "When will my refund arrive?"),
]


def test_a_call_is_metered_and_charged_to_its_bill() -> None:
    run = Run()

    async def go(url: str) -> Spend:
        gw = run.gateway(url)
        bill = Spend("wrenholt")
        SPEND.set(bill)
        await gw.chat("mock-a-fast", PROMPT)  # the cache is cold
        await gw.chat("mock-a-fast", PROMPT)  # and now warm
        await gw.aclose()
        return bill

    with running_provider() as mock:
        bill = asyncio.run(go(mock.base_url))
    first, second = run.spans.get_finished_spans()[1::2]
    assert first.attributes is not None and second.attributes
    assert first.attributes[c.CACHE_READ_TOKENS] == 0
    assert second.attributes[c.CACHE_READ_TOKENS] == 5
    assert second.attributes[c.REQUEST_MAX_TOKENS] == 512
    assert second.attributes[c.PRICE_TABLE] == "2026-10-01"
    assert second.attributes[c.TENANT] == "wrenholt"
    # 10 input tokens and 8 output, 5 of the input from the cache
    cold, warm = FAST.of(Usage(10, 8, 0)), FAST.of(Usage(10, 8, 5))
    assert bill.cost == cold + warm and bill.calls == 2
    assert second.attributes[c.CALL_COST] == float(warm)
    ((charged, dollars),) = run.values(c.COST)
    assert charged == {
        c.TENANT: "wrenholt",
        c.PROVIDER_NAME: "wrenholt.mock_a",
        c.REQUEST_MODEL: "mock-a-fast",
        c.RESPONSE_MODEL: "mock-a-fast-2026-09",
    }
    assert dollars == pytest.approx(float(cold + warm))
    (inputs,) = run.values(c.USAGE_INPUT)
    assert inputs[1] == 20 and inputs[0][c.TOKEN_MODALITY] == "text"
    assert [v for _, v in run.values(c.USAGE_CACHE_READ)] == [5]
    (per_call,) = run.values(c.OUTPUT_PER_CALL)
    assert c.RESPONSE_MODEL not in per_call[0]  # not in its budget


def test_a_streamed_call_reports_usage_at_its_end() -> None:
    run = Run()

    async def go(url: str) -> Spend:
        gw = run.gateway(url)
        bill = Spend("wrenholt")
        SPEND.set(bill)
        used = ("linnet.support", "1")
        async with aclosing(
            gw.stream("mock-a-fast", PROMPT, used)
        ) as chunks:
            words = [piece async for piece in chunks]
        await gw.aclose()
        assert len(words) == 8
        return bill

    with running_provider(streaming=FAST_STREAM) as mock:
        bill = asyncio.run(go(mock.base_url))
    assert bill.cost == FAST.of(Usage(10, 8, 0))
    (charged,) = run.values(c.COST)
    assert charged[0][c.PROMPT_VERSION] == "1"


def test_a_stream_cut_short_reports_no_usage() -> None:
    # FS-04: the stream ends after three chunks, before any usage.
    run = Run()

    async def go(url: str) -> Spend:
        gw = run.gateway(url)
        bill = Spend("wrenholt")
        SPEND.set(bill)
        with pytest.raises(ProviderError):
            async with aclosing(
                gw.stream("mock-a-fast", PROMPT)
            ) as chunks:
                async for _ in chunks:
                    pass
        await gw.aclose()
        return bill

    with running_provider(streaming=FS04_CUT) as mock:
        bill = asyncio.run(go(mock.base_url))
    assert bill.calls == 0 and bill.cost == 0
    assert run.values(c.COST) == []
    (request,) = run.spans.get_finished_spans()[-1:]
    assert c.CALL_COST not in (request.attributes or {})


def test_an_unpriced_model_still_counts_its_tokens() -> None:
    run = Run()
    meter = run.meters.get_meter("t")
    priced = CostMeter(meter, PriceTable("v", {"other": FAST}))
    route: Attrs = {
        c.OPERATION_NAME: "chat",
        c.PROVIDER_NAME: "p",
        c.REQUEST_MODEL: "m",
    }
    assert priced.record(route, "m-1", Usage(5, 2), "t", None) is None
    assert [v for _, v in run.values(c.USAGE_OUTPUT)] == [2]
    assert run.values(c.COST) == []
    assert isinstance(FAST, Price)
