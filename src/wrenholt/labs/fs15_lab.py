"""FS-15 lab (Chapter 10): quiet failures under tail sampling.

    uv run python scripts/fs15_sampling_blind_spot.py

Twenty-four answers, one at a time, through Linnet's gateway: some
are rate-limited once and retried, some stream after a 3 s wait for
the first chunk (FS-02), some come from a substituted model (FS-11)
and the rest from nothing wrong. Spans go to the pinned Collector,
whose tail-sampling processor passes the traces it keeps to a
stand-in for Tempo. The answers run twice: under the opening
incident's policies (every trace with an error, and one in twenty
of the rest) and under config.production.yaml's. Trace IDs come
from a seeded generator, so the probabilistic policies keep the
same traces on every run. Mock provider output: SIMULATED.
"""

import asyncio
import random
import time
from collections.abc import Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any

from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    HistogramDataPoint,
    InMemoryMetricReader,
    MetricsData,
    NumberDataPoint,
)
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.sdk.trace.id_generator import IdGenerator

from services.mock_llm.faults import FS15_RATE_WAVE
from services.mock_llm.model_swap import FS11_SWAP
from services.mock_llm.server import running_provider
from services.mock_llm.streaming import FS02_BROWNOUT
from services.otlp_standin import StandIn
from services.outage_lab import free_port
from wrenholt.gateway import Gateway, Message, Route
from wrenholt.labs.collector import Collector, production, total
from wrenholt.telemetry import conventions as c

MODEL = "mock-a-fast"
PINNED = {MODEL: "mock-a-fast-2026-09"}
QUESTION = [Message("user", "When will my refund arrive?")]
KINDS = ("retried", "slow", "substituted", "fine")
SLOW_S = 2.5  # the ttfc SLI's threshold (Chapter 2)
DECIDED = (
    "otelcol_processor_tail_sampling_global_count_traces_sampled"
)
VOTES = "otelcol_processor_tail_sampling_count_traces_sampled"
# The opening incident's Collector: every trace with an error, and
# one in twenty of the rest.
INCIDENT: list[dict[str, Any]] = [
    {
        "name": "errors",
        "type": "status_code",
        "status_code": {"status_codes": ["ERROR"]},
    },
    {
        "name": "baseline",
        "type": "probabilistic",
        "probabilistic": {"sampling_percentage": 5},
    },
]


def wrenholt() -> list[dict[str, Any]]:
    """The policies in config.production.yaml."""
    sampling = production()["processors"]["tail_sampling"]
    policies: list[dict[str, Any]] = sampling["policies"]
    return policies


class SeededIds(IdGenerator):
    """Trace and span IDs from a fixed seed: the same IDs, in the
    same order, on every run."""

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)

    def generate_span_id(self) -> int:
        return self._rng.getrandbits(64) or 1

    def generate_trace_id(self) -> int:
        return self._rng.getrandbits(128) or 1


def plan() -> list[str]:
    """Which mock answers each of the 24 questions, in order."""
    order = ["wave"] * 16 + ["slow"] * 4 + ["swap"] * 4
    random.Random(15).shuffle(order)
    return order


async def ask_all(
    order: Sequence[str],
    urls: dict[str, str],
    tracing: TracerProvider,
    meters: MeterProvider,
) -> None:
    tracer = tracing.get_tracer("wrenholt.labs.fs15")
    for mock in order:
        route = Route("wrenholt.mock_a", urls[mock], "sk")
        gw = Gateway(
            {MODEL: route},
            tracer_provider=tracing,
            meter_provider=meters,
            pinned=PINNED,
        )
        # The API's request span, in production: the trace's root.
        with tracer.start_as_current_span("answer"):
            if mock == "slow":
                used = ("linnet.support", "1")
                async for _ in gw.stream(MODEL, QUESTION, used):
                    pass
            else:
                await gw.chat(MODEL, QUESTION)
        await gw.aclose()


def kind(spans: list[ReadableSpan]) -> str:
    """What happened in one trace, read from its chat span."""
    for span in spans:
        attrs = span.attributes or {}
        if not span.name.startswith(f"{c.CHAT} "):
            continue
        first = attrs.get(c.RESPONSE_TIME_TO_FIRST_CHUNK, 0.0)
        if isinstance(first, float) and first >= SLOW_S:
            return "slow"
        if attrs.get(c.MODEL_MISMATCH) is True:
            return "substituted"
        count = attrs.get(c.ATTEMPT_COUNT, 1)
        if isinstance(count, int) and count > 1:
            return "retried"
    return "fine"


def shown(data: MetricsData | None) -> dict[str, int]:
    """What the dashboard's metrics show for each quiet failure."""
    found = dict.fromkeys(KINDS[:3], 0)
    for resource in data.resource_metrics if data else []:
        for scope in resource.scope_metrics:
            for m in scope.metrics:
                for p in m.data.data_points:
                    error = (p.attributes or {}).get(c.ERROR_TYPE)
                    if isinstance(p, HistogramDataPoint):
                        if m.name == c.TIME_TO_FIRST_CHUNK:
                            over = p.explicit_bounds.index(SLOW_S) + 1
                            found["slow"] += sum(
                                p.bucket_counts[over:]
                            )
                    elif isinstance(p, NumberDataPoint):
                        if (
                            m.name == c.ATTEMPTS
                            and error == "rate_limited"
                        ):
                            found["retried"] += int(p.value)
                        if m.name == c.MODEL_MISMATCHES:
                            found["substituted"] += int(p.value)
    return found


@dataclass(frozen=True)
class Outcome:
    answers: dict[str, int]  # kind: answers of that kind
    shown: dict[str, int]  # kind: what the metrics show
    kept: dict[str, int]  # kind: traces the Collector kept
    votes: dict[str, int]  # policy: traces it voted to keep


def run(policies: list[dict[str, Any]]) -> Outcome:
    order = plan()
    tempo = StandIn(free_port())
    tempo.up()
    sampling = {
        "decision_wait": "2s",  # 20s in production; the lab is short
        "num_traces": 1000,
        "policies": policies,
    }
    processors = {
        "tail_sampling": sampling,
        "batch": {"timeout": "200ms"},
    }
    produced = InMemorySpanExporter()  # everything, before sampling
    reader = InMemoryMetricReader()
    meters = MeterProvider(metric_readers=[reader])
    try:
        with Collector(processors, tempo.port) as collector:
            tracing = TracerProvider(id_generator=SeededIds(15))
            exporter = OTLPSpanExporter(endpoint=collector.endpoint)
            tracing.add_span_processor(BatchSpanProcessor(exporter))
            tracing.add_span_processor(SimpleSpanProcessor(produced))
            with ExitStack() as stack:
                mocks = {
                    "wave": running_provider(FS15_RATE_WAVE),
                    "slow": running_provider(streaming=FS02_BROWNOUT),
                    "swap": running_provider(model_swap=FS11_SWAP),
                }
                urls = {
                    name: stack.enter_context(mock).base_url
                    for name, mock in mocks.items()
                }
                asyncio.run(ask_all(order, urls, tracing, meters))
            tracing.force_flush()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if total(collector.metrics(), DECIDED) >= len(order):
                    break
                time.sleep(0.5)
            time.sleep(1.0)  # the batch processor's last export
            samples = collector.metrics()
            tracing.shutdown()
        kept_ids = {r.trace_id for r in tempo.records()}
    finally:
        tempo.down()
    traces: dict[str, list[ReadableSpan]] = {}
    for span in produced.get_finished_spans():
        tid = format(span.context.trace_id, "032x")
        traces.setdefault(tid, []).append(span)
    answers = dict.fromkeys(KINDS, 0)
    kept = dict.fromkeys(KINDS, 0)
    for tid, spans in traces.items():
        answers[kind(spans)] += 1
        kept[kind(spans)] += tid in kept_ids
    votes = {
        s.labels["policy"]: int(s.value)
        for s in samples
        if s.name == VOTES and s.labels.get("sampled") == "true"
    }
    return Outcome(
        answers, shown(reader.get_metrics_data()), kept, votes
    )


ROWS = (
    ("retried", "retried after a 429"),
    ("slow", "first chunk after 3 s"),
    ("substituted", "substituted model"),
    ("fine", "nothing wrong"),
)


def report(before: Outcome, after: Outcome) -> list[str]:
    lines = [
        "FS-15: quiet failures under tail sampling (SIMULATED)",
        f"{sum(before.answers.values())} answers, one at a time, "
        "through otelcol-contrib 0.162.0",
        f"{'':23}{'metrics':9}{'traces kept:':16}traces kept:",
        f"{'':23}{'show':9}{'errors and 5%':16}Wrenholt",
    ]
    for key, label in ROWS:
        metric = str(before.shown.get(key, "-"))
        old = f"{before.kept[key]} of {before.answers[key]}"
        new = f"{after.kept[key]} of {after.answers[key]}"
        lines.append(f"{label:23}{metric:9}{old:16}{new}")
    order = [p["name"] for p in wrenholt()]
    voted = [
        f"{n} {after.votes[n]}" for n in order if n in after.votes
    ]
    lines.append("traces each of Wrenholt's policies voted to keep:")
    lines.append("  " + ", ".join(voted))
    return lines


def main() -> None:
    before = run(INCIDENT)
    after = run(wrenholt())
    print("\n".join(report(before, after)))
