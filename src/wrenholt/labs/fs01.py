"""FS-01 hidden retry storm: what each layer saw (SIMULATED).

uv sync --group lab
uv run python scripts/fs01_hidden_retry.py
"""

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass

import openai
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from services.mock_llm.app import Received
from services.mock_llm.faults import (
    FS01_HIDDEN_RETRY_STORM,
    FaultPlan,
)
from services.mock_llm.server import running_provider
from wrenholt.labs.layered import instrument_default
from wrenholt.orchestrator.baseline import answer, make_client

MODEL = "mock-a-fast"
QUESTION = "When will my refund arrive?"
ATTEMPT_WORDS = ("retry", "attempt", "resend")


@dataclass(frozen=True)
class SpanRow:
    name: str
    parent: str | None
    start_ms: float
    duration_ms: float
    http_status: int | None
    error_type: str | None
    attempt_keys: tuple[str, ...]


@dataclass(frozen=True)
class Fs01Result:
    retries_on: bool
    outcome: str
    spans: tuple[SpanRow, ...]
    provider: tuple[Received, ...]
    t0_ns: int


def run(
    exporter: InMemorySpanExporter,
    retries_on: bool,
    plan: FaultPlan = FS01_HIDDEN_RETRY_STORM,
) -> Fs01Result:
    exporter.clear()
    with running_provider(plan) as mock:
        client = make_client(mock.base_url, "sk-mock")
        if not retries_on:
            client = client.with_options(max_retries=0)
        try:
            outcome = answer(client, MODEL, QUESTION)
        except openai.APIStatusError as exc:
            outcome = type(exc).__name__
        received = tuple(mock.log.items())
    spans = exporter.get_finished_spans()
    return summarize(retries_on, outcome, spans, received)


def summarize(
    retries_on: bool,
    outcome: str,
    spans: Sequence[ReadableSpan],
    received: tuple[Received, ...],
) -> Fs01Result:
    t0 = min(s.start_time or 0 for s in spans)
    names = {s.context.span_id: s.name for s in spans if s.context}
    rows = []
    for s in sorted(spans, key=lambda x: x.start_time or 0):
        attrs = dict(s.attributes or {})
        status = attrs.get("http.response.status_code")
        error = attrs.get("error.type")
        parent = names.get(s.parent.span_id) if s.parent else None
        start, end = s.start_time or 0, s.end_time or 0
        keys = tuple(
            k for k in attrs if any(w in k for w in ATTEMPT_WORDS)
        )
        rows.append(
            SpanRow(
                name=s.name,
                parent=parent,
                start_ms=(start - t0) / 1e6,
                duration_ms=(end - start) / 1e6,
                http_status=int(str(status)) if status else None,
                error_type=str(error) if error else None,
                attempt_keys=keys,
            )
        )
    return Fs01Result(retries_on, outcome, tuple(rows), received, t0)


def report(result: Fs01Result) -> str:
    mode = "on (SDK default)" if result.retries_on else "off"
    lines = [
        f"FS-01 (SIMULATED), SDK retries {mode}",
        f"outcome: {result.outcome}",
        f"{'span':<20}{'start ms':>10}{'dur ms':>10}"
        f"{'http':>6}  error.type",
    ]
    for row in result.spans:
        name = ("  " if row.parent else "") + row.name
        http = str(row.http_status or "-")
        lines.append(
            f"{name:<20}{row.start_ms:>10.1f}{row.duration_ms:>10.1f}"
            f"{http:>6}  {row.error_type or '-'}"
        )
    statuses = ", ".join(str(r.status) for r in result.provider)
    counts = ", ".join(r.retry_count or "-" for r in result.provider)
    lines.append(f"provider saw {len(result.provider)}: {statuses}")
    lines.append(f"x-stainless-retry-count: {counts}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", help="write both runs as JSON")
    args = parser.parse_args(argv)
    exporter = InMemorySpanExporter()
    instrument_default(exporter)
    results = [run(exporter, True), run(exporter, False)]
    print("\n\n".join(report(r) for r in results))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as out:
            json.dump([asdict(r) for r in results], out, indent=2)
