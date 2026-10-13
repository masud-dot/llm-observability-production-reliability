"""Rename drill (Chapter 5): one mapped name changes upstream.

    uv run python scripts/rename_drill.py

Linnet's gateway runs FS-01 twice: as pinned, then with one
mapped name changed, as an upgrade that renames an attribute
would change it. The dashboard keeps answering, so nothing
fails; the drift checks are what notice.
"""

import asyncio
import textwrap
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    HistogramDataPoint,
    InMemoryMetricReader,
)
from opentelemetry.sdk.trace import TracerProvider

from services.mock_llm.faults import FS01_HIDDEN_RETRY_STORM
from services.mock_llm.server import running_provider
from wrenholt.gateway import Gateway, Message, Route
from wrenholt.slo import rules
from wrenholt.telemetry import conventions, drift

ROOT = Path(__file__).resolve().parents[3]
BOARDS = sorted(
    (ROOT / "deploy/compose/grafana/provisioning/dashboards").glob(
        "*.json"
    )
)
OLD, NEW = "gen_ai.provider.name", "gen_ai.system"
Metric = tuple[str, str, str, set[str]]


@dataclass(frozen=True)
class Outcome:
    missing: list[str]  # dashboard labels the run did not produce
    problems: list[str]  # what the drift checks report


@contextmanager
def renamed(on: bool) -> Iterator[tuple[conventions.Name, ...]]:
    """The one-line change, made in memory and undone after."""
    registry = conventions.REGISTRY
    if not on:
        yield registry
        return
    conventions.PROVIDER_NAME = NEW  # type: ignore[misc]
    try:
        yield tuple(
            replace(n, name=NEW) if n.name == OLD else n
            for n in registry
        )
    finally:
        conventions.PROVIDER_NAME = OLD  # type: ignore[misc]


def gateway_metrics() -> list[Metric]:
    reader = InMemoryMetricReader()
    meters = MeterProvider(metric_readers=[reader])
    with running_provider(FS01_HIDDEN_RETRY_STORM) as mock:
        route = Route("wrenholt.mock_a", mock.base_url, "sk-mock")

        async def ask() -> None:
            gw = Gateway(
                {"mock-a-fast": route},
                tracer_provider=TracerProvider(),
                meter_provider=meters,
                sleep=lambda _: asyncio.sleep(0),
            )
            await gw.chat("mock-a-fast", [Message("user", "Refund?")])
            await gw.aclose()

        asyncio.run(ask())
    found: list[Metric] = []
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
                found.append((m.name, kind, m.unit or "", keys))
    return found


def drill(on: bool) -> Outcome:
    with renamed(on) as registry:
        series, labels = drift.produced(gateway_metrics())
        missing = []
        for board in BOARDS:
            for expr in drift.prometheus_queries(board):
                used, grouped = drift.promql_names(expr)
                if not used <= series:
                    continue  # a panel the gateway does not feed
                missing += sorted(grouped - labels)
        problems = drift.against_snapshot(
            registry, drift.load_snapshot()
        )
        # Chapter 10: the pipeline dashboard reads the Collector's
        # own names, which its snapshot lists.
        collector = drift.load_collector_snapshot()
        # Chapter 12: and the series the SLO rules record.
        known = {**collector, **rules.recorded()}
        problems += drift.lint_dashboards(BOARDS, registry, known)
    return Outcome(sorted(set(missing)), problems)


def main() -> None:
    print("Rename drill (mock provider: SIMULATED)")
    print(f"one mapped name changes: {OLD} -> {NEW}")
    for label, on in (("as pinned", False), ("renamed", True)):
        outcome = drill(on)
        gone = ", ".join(outcome.missing) or "none"
        print(f"{label}: dashboard labels the run lacks: {gone}")
        print(f"  drift problems: {len(outcome.problems)}")
        for problem in outcome.problems:
            lines = textwrap.wrap(problem, 64)
            print("  - " + "\n    ".join(lines))
