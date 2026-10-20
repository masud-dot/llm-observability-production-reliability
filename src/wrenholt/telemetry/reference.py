"""The telemetry contract reference (Appendix A).

Generated from the repository, never written by hand: names and
their sources from the conventions module, data classes, handling
and retention from the privacy contract, label sets and series from
the cardinality budget, and tail-sampling policies from the
production Collector configuration. The drift tests fail when the
committed reference and this output differ.

    uv run python scripts/contract_reference.py [--check]
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from wrenholt.privacy.contract import (
    FIELDS,
    HANDLING,
    NEVER_EXPORTED,
    RETENTION_DAYS,
)
from wrenholt.telemetry import conventions as c
from wrenholt.telemetry.drift import stable_core_names

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / "docs" / "telemetry_contract.md"
COLLECTOR = ROOT / "deploy/compose/otelcol/config.production.yaml"
STATUS = {"genai": "Development", "core": "Stable", "book": "book"}
RESOURCE = (
    "service.name", c.SERVICE_NAMESPACE, c.SERVICE_VERSION,
    c.DEPLOYMENT_ENVIRONMENT, "telemetry.sdk.language",
    "telemetry.sdk.name", "telemetry.sdk.version",
)  # fmt: skip


@dataclass(frozen=True)
class Span:
    name: str  # {key}: that attribute's value
    status: str
    module: str
    code: str  # how the module spells the name


SPANS = (
    Span("invoke_agent {gen_ai.agent.name}", "Development",
         "src/wrenholt/orchestrator/linnet.py",
         'f"{c.INVOKE_AGENT} {AGENT}"'),
    Span("build context", "book",
         "src/wrenholt/orchestrator/linnet.py", '"build context"'),
    Span("retrieval {gen_ai.data_source.id}", "Development",
         "src/wrenholt/rag/retriever.py",
         'f"{c.RETRIEVAL} {SOURCE}"'),
    Span("embeddings {gen_ai.request.model}", "Development",
         "src/wrenholt/rag/retriever.py",
         'f"{c.EMBEDDINGS} {model.name}"'),
    Span("chat {gen_ai.request.model}", "Development",
         "src/wrenholt/gateway/client.py", 'f"{c.CHAT} {model}"'),
    Span("attempt {gen_ai.provider.name}", "book",
         "src/wrenholt/gateway/client.py",
         'f"attempt {route.provider}"'),
    Span("execute_tool {gen_ai.tool.name}", "Development",
         "src/wrenholt/tools/toolbox.py",
         'f"{c.EXECUTE_TOOL} {call.name}"'),
    Span("wrenholt.guardrail", "book",
         "src/wrenholt/guardrail.py", "c.GUARDRAIL,"),
    Span("record reproduction bundle", "book",
         "src/wrenholt/repro.py", '"record reproduction bundle"'),
)  # fmt: skip
EVENTS = (  # name, status, carried by
    (c.EVALUATION_RESULT, "Development", "log record (Chapter 13)"),
    (c.RETRY_EVENT, "book", "chat span (Chapter 16)"),
    (c.BREAKER_EVENT, "book", "chat span (Chapter 16)"),
    (c.FALLBACK_EVENT, "book", "chat span (Chapter 17)"),
)


def status(name: str, stable: set[str]) -> str:
    for n in c.REGISTRY:
        if n.name == name:
            return STATUS[n.source]
    if name.startswith("wrenholt."):
        return "book"
    return "Stable" if name in stable else "Development"


def table(head: tuple[str, ...], rows: list[tuple[Any, ...]]) -> str:
    lines = ["| " + " | ".join(head) + " |"]
    lines.append("|" + "---|" * len(head))
    lines += [
        "| " + " | ".join(str(x) for x in r) + " |" for r in rows
    ]
    return "\n".join(lines)


def labels() -> dict[str, list[str]]:
    """Each attribute's metrics, from the cardinality budget."""
    on: dict[str, list[str]] = {}
    for b in c.BUDGET:
        for a in b.attributes:
            on.setdefault(a, []).append(b.metric)
    return on


def policies() -> list[tuple[str, str]]:
    config = yaml.safe_load(COLLECTOR.read_text())
    sampling = config["processors"]["tail_sampling"]["policies"]
    return [(p["name"], p["type"]) for p in sampling]


def tables() -> dict[str, str]:
    stable = stable_core_names()
    on = labels()
    keys = {n.name for n in c.REGISTRY if n.kind == "attribute"}
    keys |= set(FIELDS) - set(RESOURCE)
    attributes = [
        (f"`{k}`", status(k, stable), FIELDS[k].value,
         len(on.get(k, [])) or "-")
        for k in sorted(keys)
    ]  # fmt: skip
    metrics: list[tuple[Any, ...]] = [
        (f"`{b.metric}`", n.instrument, f"`{n.unit}`",
         STATUS[n.source], len(b.attributes), b.series)
        for b in c.BUDGET
        for n in c.REGISTRY
        if n.name == b.metric
    ]  # fmt: skip
    total = sum(b.series for b in c.BUDGET)
    metrics.append(("total", "", "", "", "", total))
    return {
        "resource": table(
            ("Attribute", "Status", "Data class"),
            [(f"`{k}`", status(k, stable), FIELDS[k].value)
             for k in RESOURCE],
        ),
        "spans": table(
            ("Span name", "Status", "Emitted in"),
            [(f"`{s.name}`", s.status, f"`{s.module[4:]}`")
             for s in SPANS],
        ),
        "events": table(
            ("Event", "Status", "Carried by"),
            [(f"`{n}`", st, by) for n, st, by in EVENTS],
        ),
        "attributes": table(
            ("Attribute", "Status", "Data class", "Metrics"),
            attributes,
        ),
        "metrics": table(
            ("Metric", "Instrument", "Unit", "Status", "Labels",
             "Series"),
            metrics,
        ),
        "never": table(
            ("Key", "Data class", "Handling"),
            [(f"`{k}`", v.value, HANDLING[v][0])
             for k, v in sorted(NEVER_EXPORTED.items())],
        ),
        "handling": table(
            ("Data class", "Handling", "Retention", "Who reads"),
            [(k.value, *v) for k, v in HANDLING.items()],
        ),
        "retention": table(
            ("Signal", "Store", "Days"),
            [(s, b, RETENTION_DAYS[s]) for s, b in (
                ("metrics", "Prometheus"), ("traces", "Tempo"),
                ("logs", "Loki"))],
        ),
        "sampling": table(
            ("Policy", "Type"),
            [(f"`{n}`", f"`{t}`") for n, t in policies()],
        ),
    }  # fmt: skip


TITLES = {
    "resource": "Resource attributes",
    "spans": "Spans",
    "events": "Events",
    "attributes": "Attributes",
    "metrics": "Metrics",
    "never": "Never exported",
    "handling": "Handling by data class",
    "retention": "Retention by signal",
    "sampling": "Tail-sampling policies",
}


def render() -> str:
    parts = [
        "# Telemetry contract reference\n",
        "Generated by `scripts/contract_reference.py`; do not edit.",
        f"GenAI names pinned at `{c.GENAI_COMMIT[:7]}`.\n",
    ]
    for key, body in tables().items():
        parts += [f"## {TITLES[key]}\n", body + "\n"]
    return "\n".join(parts)


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        same = REFERENCE.read_text() == text
        print(
            "reference is current" if same else "reference is stale"
        )
        return 0 if same else 1
    REFERENCE.write_text(text)
    print(f"wrote {REFERENCE.relative_to(ROOT)}")
    return 0
