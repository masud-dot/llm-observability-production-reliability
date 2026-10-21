"""Collector overload lab (Chapter 10): accepted, then dropped.

    uv run python scripts/collector_overload.py

A burst of 2,000 spans in 20 exports of 100 reaches the pinned
Collector. Its backend, a stand-in for Tempo, answers each request
after 0.25 s, and one consumer drains the export queue. Three
pipelines take the same burst: the batch processor with a queue of
3 requests, the batch processor with a queue of 30, and no batch
processor with a queue of 3. The lab compares what the SDK was
told, what the Collector counted and what the backend stored.
"""

import time
from dataclasses import dataclass
from typing import Any

from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExportResult,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from services.otlp_standin import StandIn
from services.outage_lab import free_port
from wrenholt.labs.collector import Collector, total

SPANS, PER_EXPORT = 2000, 100
BACKEND_S = 0.25  # the slow backend's answer time
BATCH = {"send_batch_size": 100, "send_batch_max_size": 100}
CASES = ((True, 3), (True, 30), (False, 3))


def burst() -> list[ReadableSpan]:
    made = InMemorySpanExporter()
    tracing = TracerProvider()
    tracing.add_span_processor(SimpleSpanProcessor(made))
    tracer = tracing.get_tracer("wrenholt.labs.overload")
    for i in range(SPANS):
        with tracer.start_as_current_span(f"burst {i}"):
            pass
    return list(made.get_finished_spans())


@dataclass(frozen=True)
class Result:
    failed: int  # exports the SDK was told failed
    seconds: float  # how long the SDK spent exporting
    refused: int  # spans the receiver refused
    rejected: int  # spans the export queue could not take
    stored: int  # spans the backend received


def run(batch: bool, queue: int, spans: list[ReadableSpan]) -> Result:
    tempo = StandIn(free_port())
    tempo.delay_s = BACKEND_S
    tempo.up()
    processors: dict[str, Any] = (
        {"batch": {**BATCH, "timeout": "100ms"}} if batch else {}
    )
    exporter = {
        "sending_queue": {"queue_size": queue, "num_consumers": 1}
    }
    try:
        with Collector(processors, tempo.port, exporter) as collector:
            sdk = OTLPSpanExporter(
                endpoint=collector.endpoint, timeout=10
            )
            failed, start = 0, time.perf_counter()
            for i in range(0, len(spans), PER_EXPORT):
                done = sdk.export(spans[i : i + PER_EXPORT])
                failed += done is not SpanExportResult.SUCCESS
            seconds = time.perf_counter() - start
            stored, deadline = -1, time.monotonic() + 60
            while time.monotonic() < deadline:
                time.sleep(1.5)
                now = len(tempo.records())
                if now == stored:  # the queue has drained
                    break
                stored = now
            samples = collector.metrics()
    finally:
        tempo.down()
    return Result(
        failed,
        seconds,
        int(total(samples, "otelcol_receiver_refused_spans")),
        int(total(samples, "otelcol_exporter_enqueue_failed_spans")),
        stored,
    )


def report(results: list[Result]) -> list[str]:
    heads = [
        ("batch," if batch else "no batch,", f"queue {queue}")
        for batch, queue in CASES
    ]
    rows = (
        (
            "exports the SDK saw fail",
            [str(r.failed) for r in results],
        ),
        (
            "seconds the SDK waited",
            [f"{r.seconds:.1f}" for r in results],
        ),
        (
            "refused by the receiver",
            [str(r.refused) for r in results],
        ),
        ("rejected by the queue", [str(r.rejected) for r in results]),
        ("stored by the backend", [str(r.stored) for r in results]),
    )
    lines = [
        "Collector overload: accepted, then dropped (SIMULATED)",
        f"{SPANS:,} spans in {SPANS // PER_EXPORT} exports; "
        f"the backend answers in {BACKEND_S} s",
        f"{'':27}" + "".join(f"{a:11}" for a, _ in heads),
        f"{'':27}" + "".join(f"{b:11}" for _, b in heads),
    ]
    for label, cells in rows:
        lines.append(
            f"{label:27}" + "".join(f"{x:11}" for x in cells)
        )
    return [line.rstrip() for line in lines]


def main() -> None:
    spans = burst()
    results = [run(batch, queue, spans) for batch, queue in CASES]
    print("\n".join(report(results)))
