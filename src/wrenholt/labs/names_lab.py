"""Names lab (Chapter 5): the pinned specification against what
the pinned Python packages emit (SIMULATED workload).

    uv sync --group lab
    uv run python scripts/names_lab.py

Instrumentations read OTEL_SEMCONV_STABILITY_OPT_IN once, at their
first instrument() call, so each setting runs in its own process.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes,
)
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics

from wrenholt.telemetry import drift

ROOT = Path(__file__).resolve().parents[3]
PROBE = """
import json, sys
sys.path[:0] = [sys.argv[1] + "/src", sys.argv[1]]
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter)
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from services.mock_llm.server import running_provider
from wrenholt.orchestrator.baseline import answer, make_client
spans, reader = InMemorySpanExporter(), InMemoryMetricReader()
tracing = TracerProvider()
tracing.add_span_processor(SimpleSpanProcessor(spans))
OpenAIInstrumentor().instrument(
    tracer_provider=tracing,
    meter_provider=MeterProvider(metric_readers=[reader]))
with running_provider() as mock:
    answer(make_client(mock.base_url, "sk"), "mock-a-fast", "Refund?")
attrs = sorted({k for s in spans.get_finished_spans()
                for k in (s.attributes or {})})
data = reader.get_metrics_data()
found = [m for r in data.resource_metrics
         for sc in r.scope_metrics for m in sc.metrics]
names = sorted(m.name for m in found)
keys = sorted({k for m in found for p in m.data.data_points
               for k in (p.attributes or {})})
print(json.dumps({"attributes": attrs, "metrics": names,
                  "metric_attributes": keys}))
"""


def emitted(opt_in: str | None) -> dict[str, list[str]]:
    """Span attributes, metric names and metric attribute keys the
    official OpenAI instrumentation emits for one chat under one
    opt-in value."""
    env = dict(os.environ)
    env.pop("OTEL_SEMCONV_STABILITY_OPT_IN", None)
    if opt_in is not None:
        env["OTEL_SEMCONV_STABILITY_OPT_IN"] = opt_in
    run = subprocess.run(
        [sys.executable, "-c", PROBE, str(ROOT)],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    data: dict[str, list[str]] = json.loads(
        run.stdout.splitlines()[-1]
    )
    return data


def package() -> tuple[set[str], set[str]]:
    """GenAI attribute and metric names in the pinned package."""

    def names(module: Any) -> set[str]:
        return {
            v
            for k, v in vars(module).items()
            if k.startswith("GEN_AI_") and isinstance(v, str)
        }

    return names(gen_ai_attributes), names(gen_ai_metrics)


def provider(attrs: list[str]) -> str:
    for name in ("gen_ai.provider.name", "gen_ai.system"):
        if name in attrs:
            return name
    return "-"


def tokens(metrics: list[str]) -> str:
    """Token-count metrics only, not the server timing ones."""
    usage = [
        m for m in metrics if m.endswith(("token.usage", "_tokens"))
    ]
    return ", ".join(usage) or "-"


LATEST = "gen_ai_latest_experimental"
OPT_INS: tuple[tuple[str, str | None], ...] = (
    ("official instrumentation, opt-in unset", None),
    (f"official, opt-in {LATEST}", LATEST),
)


def line(label: str, value: str) -> None:
    print(f"  {label:<23}{value}")


def main() -> None:
    snap = drift.load_snapshot()
    spec = {k for k in snap["attributes"] if k.startswith("gen_ai.")}
    usage = sum(".inference.usage." in m for m in snap["metrics"])
    per_op = sum(
        ".inference.operation." in m for m in snap["metrics"]
    )
    pkg_attrs, pkg_metrics = package()
    dropped = pkg_attrs - spec
    shown = [
        n
        for n in ("gen_ai.system", "gen_ai.token.type")
        if n in dropped
    ]
    gone = f"{len(dropped)}, e.g. {', '.join(shown)}"
    print("GenAI names: pinned specification against pinned packages")
    print(f"specification @ {snap['commit'][:7]} (all Development)")
    line("provider attribute", provider(sorted(spec)))
    line(
        "token metrics", f"gen_ai.client.inference.usage.* ({usage}),"
    )
    line("", f"gen_ai.client.inference.operation.* ({per_op})")
    print("opentelemetry-semantic-conventions 0.66b0")
    line("token metric", tokens(sorted(pkg_metrics)))
    line("names not in the spec", gone)
    for title, opt_in in OPT_INS:
        got = emitted(opt_in)
        print(title)
        line("provider attribute", provider(got["attributes"]))
        line("token metric", tokens(got["metrics"]))
