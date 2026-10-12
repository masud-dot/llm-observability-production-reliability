"""Drift checks: what Wrenholt emits against what it pins.

Each check returns a list of problems, empty when all is well, so
the drift tests assert on it and the rename drill can print it.
"""

import importlib
import json
import pkgutil
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import opentelemetry.semconv.attributes as stable_attributes

from wrenholt.telemetry import promnames
from wrenholt.telemetry.conventions import CONTENT, Name

SNAPSHOT = Path(__file__).with_name("genai_snapshot.json")
PROMQL_WORDS = {
    "sum", "by", "without", "on", "ignoring", "group_left",
    "group_right", "rate", "irate", "increase", "delta", "avg",
    "min", "max", "count", "topk", "bottomk", "histogram_quantile",
    "and", "or", "unless", "bool", "offset",
}  # fmt: skip
LABELS_ALWAYS = {"le", "job", "instance"}
TRACEQL_INTRINSICS = {"name", "status", "duration", "kind"}
UNKNOWN = "which no registered name produces"


def load_snapshot(path: Path = SNAPSHOT) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text())
    return data


def against_snapshot(
    registry: Iterable[Name], snapshot: dict[str, Any]
) -> list[str]:
    """GenAI names must exist at the pinned commit; book names must
    live under wrenholt. and never shadow a specification name."""
    pin = snapshot["commit"][:7]
    found = []
    for n in registry:
        table = snapshot[
            "attributes" if n.kind == "attribute" else "metrics"
        ]
        if n.source == "genai":
            spec = table.get(n.name)
            if spec is None:
                found.append(
                    f"{n.name}: not in the GenAI conventions @ {pin}"
                )
            elif n.kind == "metric" and (
                spec["instrument"],
                spec["unit"],
            ) != (n.instrument, n.unit):
                found.append(
                    f"{n.name}: instrument or unit differs @ {pin}"
                )
        if n.source == "book":
            if not n.name.startswith("wrenholt."):
                found.append(
                    f"{n.name}: book names live under wrenholt."
                )
            if (
                n.name in snapshot["attributes"]
                or n.name in snapshot["metrics"]
            ):
                found.append(
                    f"{n.name}: shadows a specification name"
                )
    return found


def stable_core_names() -> set[str]:
    names = set()
    for info in pkgutil.iter_modules(stable_attributes.__path__):
        module = importlib.import_module(
            f"{stable_attributes.__name__}.{info.name}"
        )
        names |= {
            v
            for k, v in vars(module).items()
            if k.isupper() and isinstance(v, str)
        }
    return names


def against_core(registry: Iterable[Name]) -> list[str]:
    """Core names must be Stable in the pinned Python package:
    opentelemetry-semantic-conventions, non-incubating modules."""
    stable = stable_core_names()
    return [
        f"{n.name}: not a Stable core name"
        for n in registry
        if n.source == "core" and n.name not in stable
    ]


def against_emitted(
    registry: Iterable[Name], attributes: set[str], metrics: set[str]
) -> list[str]:
    """Everything emitted is registered; content is never emitted."""
    names = {n.name for n in registry}
    found = [
        f"{a}: emitted but not registered"
        for a in sorted(attributes - names)
    ]
    found += [
        f"{m}: metric emitted but not registered"
        for m in sorted(metrics - names)
    ]
    found += [
        f"{a}: content attribute emitted"
        for a in sorted(attributes & set(CONTENT))
    ]
    return found


def promql_names(expr: str) -> tuple[set[str], set[str]]:
    """Metric names and label names a PromQL expression uses."""
    text = re.sub(r'"[^"]*"', '""', expr)
    text = re.sub(r"\[[^\]]*\]", "", text)
    grouping = r"\b(?:by|without|on|ignoring)\s*\(([^)]*)\)"
    labels = {
        x.strip()
        for g in re.findall(grouping, text)
        for x in g.split(",")
    } - {""}
    for matcher in re.findall(r"\{([^}]*)\}", text):
        labels |= set(
            re.findall(r"([A-Za-z_]\w*)\s*(?:=~|!~|!=|=)", matcher)
        )
    bare = re.sub(grouping, "", re.sub(r"\{[^}]*\}", "", text))
    words = set(re.findall(r"\b[A-Za-z_:][\w:]*", bare))
    return words - PROMQL_WORDS, labels


def traceql_names(query: str) -> set[str]:
    return set(re.findall(r"\b(?:span|resource)\.([\w.]+)", query))


def prometheus_queries(path: Path) -> list[str]:
    board = json.loads(path.read_text())
    return [
        t["expr"]
        for panel in board.get("panels", [])
        for t in panel.get("targets", [])
        if "expr" in t
    ]


def lint_dashboards(
    paths: Iterable[Path], registry: Iterable[Name]
) -> list[str]:
    """Every name a dashboard query uses must come from a
    registered name, as Prometheus or Tempo stores it."""
    names = list(registry)
    attributes = {n.name for n in names if n.kind == "attribute"}
    series = set().union(
        *(
            promnames.series(n.name, n.instrument, n.unit)
            for n in names
            if n.kind == "metric"
        )
    )
    labels = {promnames.label(a) for a in attributes} | LABELS_ALWAYS
    found = []
    for path in paths:
        board = json.loads(path.read_text())
        for panel in board.get("panels", []):
            title = panel.get("title", "?")
            for target in panel.get("targets", []):
                where = f"{path.name}: panel '{title}'"
                if "expr" in target:
                    used, grouped = promql_names(target["expr"])
                    found += [
                        f"{where} uses {m}, {UNKNOWN}"
                        for m in sorted(used - series)
                    ]
                    found += [
                        f"{where} uses label {x}, {UNKNOWN}"
                        for x in sorted(grouped - labels)
                    ]
                if "query" in target:
                    used = (
                        traceql_names(target["query"])
                        - TRACEQL_INTRINSICS
                    )
                    found += [
                        f"{where} uses {a}, which is not registered"
                        for a in sorted(used - attributes)
                    ]
    return found


def produced(
    metrics: Iterable[tuple[str, str, str, set[str]]],
) -> tuple[set[str], set[str]]:
    """Prometheus series and labels a run produces, from
    (name, instrument, unit, attribute keys) per emitted metric."""
    series: set[str] = set()
    labels: set[str] = set(LABELS_ALWAYS)
    for name, instrument, unit, keys in metrics:
        series |= promnames.series(name, instrument, unit)
        labels |= {promnames.label(k) for k in keys}
    return series, labels
