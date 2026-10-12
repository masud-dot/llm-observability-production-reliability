"""FS-02 lab (Chapter 8): a provider brownout (SIMULATED).

    uv run python scripts/fs02_brownout.py

Twenty streamed answers before the brownout and twenty during it,
ten at a time, through the gateway with in-memory metrics. The
brownout delays only the first chunk: the provider queues the
request, then streams at its usual pace.
"""

import asyncio
import math
from contextlib import aclosing
from dataclasses import dataclass
from typing import Any

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from services.mock_llm.server import running_provider
from services.mock_llm.streaming import (
    FS02_BROWNOUT,
    STEADY,
    Schedule,
)
from wrenholt.gateway import Gateway, Message, Route, StreamResult
from wrenholt.slo.request_map import load_request_map
from wrenholt.telemetry import conventions as c

MODEL = "mock-a-fast"
MESSAGES = [Message("user", "When will my refund arrive?")]
ANSWERS, AT_ONCE = 20, 10
THRESHOLD = c.SLI_THRESHOLDS[0]  # interactive answers (Chapter 2)
DEADLINE = load_request_map().deadline_s  # Chapter 2


@dataclass(frozen=True)
class Phase:
    results: list[StreamResult]
    within: int  # first chunks within the threshold, from its bucket
    recorded: int  # first chunks recorded
    gap_mean: float  # time per output chunk, mean


def points(reader: InMemoryMetricReader, name: str) -> list[Any]:
    data = reader.get_metrics_data()
    return [
        p
        for r in (data.resource_metrics if data else [])
        for s in r.scope_metrics
        for m in s.metrics
        if m.name == name
        for p in m.data.data_points
    ]


def within(
    reader: InMemoryMetricReader, name: str, bound: float
) -> int:
    """Good events read from one histogram bucket, as Prometheus
    reads le="2.5": exact only because 2.5 is a boundary."""
    count = 0
    for p in points(reader, name):
        k = list(p.explicit_bounds).index(bound)
        count += sum(p.bucket_counts[: k + 1])
    return count


def p95(values: list[float]) -> float:
    ranked = sorted(values)
    return ranked[math.ceil(0.95 * len(ranked)) - 1]


def phase(schedule: Schedule) -> Phase:
    reader = InMemoryMetricReader()
    meters = MeterProvider(metric_readers=[reader])

    async def one(gw: Gateway) -> StreamResult:
        done = StreamResult()
        stream = gw.stream(MODEL, MESSAGES, None, done)
        async with aclosing(stream) as chunks:
            async for _ in chunks:
                pass
        return done

    with running_provider(streaming=schedule) as mock:
        route = Route("wrenholt.mock_a", mock.base_url, "sk-mock")

        async def go() -> list[StreamResult]:
            gw = Gateway({MODEL: route}, meter_provider=meters)
            results: list[StreamResult] = []
            for _ in range(ANSWERS // AT_ONCE):
                wave = [one(gw) for _ in range(AT_ONCE)]
                results += await asyncio.gather(*wave)
            await gw.aclose()
            return results

        results = asyncio.run(go())
    ttfc = points(reader, c.TIME_TO_FIRST_CHUNK)
    gaps = points(reader, c.TIME_PER_OUTPUT_CHUNK)
    return Phase(
        results,
        within(reader, c.TIME_TO_FIRST_CHUNK, THRESHOLD),
        sum(p.count for p in ttfc),
        sum(p.sum for p in gaps) / sum(p.count for p in gaps),
    )


def main() -> None:
    steady, brownout = phase(STEADY), phase(FS02_BROWNOUT)

    def first(p: Phase) -> str:
        waits = [r.first_chunk_s or 0.0 for r in p.results]
        return f"{p95(waits):.2f} s"

    def total(p: Phase) -> str:
        return (
            f"{p95([r.duration_s or 0.0 for r in p.results]):.2f} s"
        )

    def done(p: Phase) -> str:
        ok = sum(r.error is None for r in p.results)
        return f"{ok} of {len(p.results)}"

    rows = [
        ("time to first chunk, p95", first(steady), first(brownout),
         f"{THRESHOLD} s threshold"),
        (f"first chunk within {THRESHOLD} s",
         f"{steady.within} of {steady.recorded}",
         f"{brownout.within} of {brownout.recorded}", "ttfc SLI"),
        ("time per output chunk, mean", f"{steady.gap_mean:.2f} s",
         f"{brownout.gap_mean:.2f} s", ""),
        ("duration, p95", total(steady), total(brownout),
         f"{DEADLINE} s deadline"),
        ("answers completed", done(steady), done(brownout), ""),
    ]  # fmt: skip
    print("FS-02: a provider brownout (mock provider: SIMULATED)")
    print(
        f"{ANSWERS} streamed answers per phase, {AT_ONCE} at a time"
    )
    print(f"{'':<29}{'steady':<11}{'brownout':<11}against")
    for label, a, b, against in rows:
        print(f"{label:<29}{a:<11}{b:<11}{against}".rstrip())
