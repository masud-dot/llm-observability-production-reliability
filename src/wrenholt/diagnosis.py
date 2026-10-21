"""Diagnosing production AI failures (Chapter 15).

    uv run python scripts/wrenholt_cli.py diagnose

An investigation attributes the layer first. It compares the alert's
window with the window before it, layer by layer, from telemetry
that holds no content: the provider's wait (L1), the model's
behaviour (L2), retrieval (L3). Content is read only through the
vault, by an investigator with a reason, and only to reproduce.
"""

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wrenholt.telemetry import conventions as c

Trace = dict[str, Any]
THRESHOLD_S = 2.5  # the interactive first-chunk SLO's threshold


@dataclass(frozen=True)
class Spread:
    n: int
    mean: float
    p50: float
    p95: float
    over: int  # values over the threshold


def quantile(ordered: list[float], q: float) -> float:
    """Nearest rank: the smallest value with q of them at or below."""
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def spread(values: Iterable[float], threshold: float) -> Spread:
    ordered = sorted(values)
    return Spread(
        len(ordered),
        round(sum(ordered) / len(ordered), 2),
        quantile(ordered, 0.5),
        quantile(ordered, 0.95),
        sum(v > threshold for v in ordered),
    )


@dataclass(frozen=True)
class Finding:
    layer: str
    what: str
    evidence: str
    exemplar: str  # a trace ID to open
    query: str  # where to look in production


def named(t: Trace, prefix: str) -> list[dict[str, Any]]:
    return [s for s in t["spans"] if s["name"].startswith(prefix)]


def before_model_s(t: Trace) -> float:
    """Linnet's own time before it first called the model."""
    start = t["spans"][0]["start_ns"]
    chat = named(t, f"{c.CHAT} ")[0]
    return float(chat["start_ns"] - start) / 1e9


def provider_wait_s(t: Trace) -> float:
    return float(t["first_chunk_s"]) - before_model_s(t)


def median(values: list[float]) -> float:
    return quantile(sorted(values), 0.5)


def provider(
    before: list[Trace], after: list[Trace]
) -> Finding | None:
    """L1: the wait for the first chunk grew, and Linnet's own time
    did not."""
    rise = median([provider_wait_s(t) for t in after]) - median(
        [provider_wait_s(t) for t in before]
    )
    own = median([before_model_s(t) for t in after]) - median(
        [before_model_s(t) for t in before]
    )
    if rise < 1.0 or own > 0.1:
        return None
    own = round(own, 2) + 0.0  # no "-0.00"
    worst = max(after, key=provider_wait_s)
    name = named(worst, f"{c.CHAT} ")[0]["attributes"]
    return Finding(
        "L1",
        f"provider {name[c.PROVIDER_NAME]}: first chunk"
        f" median +{rise:.2f} s",
        f"Linnet's own time before the model: {own:+.2f} s",
        worst["trace"],
        "histogram_quantile(0.5, sum by (le) (rate("
        "wrenholt_answer_time_to_first_chunk_seconds_bucket[5m])))",
    )


def empty(t: Trace) -> bool:
    found = named(t, f"{c.RETRIEVAL} ")
    return bool(found) and not found[0]["attributes"].get(
        c.RETRIEVAL_DOCUMENTS
    )


def retrieval(
    before: list[Trace], after: list[Trace]
) -> Finding | None:
    """L3: retrievals came back empty, and the index was built with
    another embedder than the one embedding the questions."""
    now = [t for t in after if empty(t)]
    if len(now) <= sum(empty(t) for t in before):
        return None
    t = now[0]
    built = named(t, f"{c.RETRIEVAL} ")[0]["attributes"]
    asked = named(t, f"{c.EMBEDDINGS} ")[0]["attributes"]
    index, query = built[c.INDEX_EMBEDDER], asked[c.REQUEST_MODEL]
    return Finding(
        "L3",
        f"retrieval: {len(now)} of {len(after)} returned nothing",
        f"index built with {index}, questions with {query}",
        t["trace"],
        '{ span.gen_ai.operation.name = "retrieval"'
        f' && span.wrenholt.index.embedder = "{index}" }}',
    )


def model(before: list[Trace], after: list[Trace]) -> Finding | None:
    """L2: finish reasons or tool calls changed."""

    def shape(ts: list[Trace]) -> set[str]:
        return {
            str(s["attributes"].get(c.FINISH_REASONS))
            for t in ts
            for s in named(t, f"{c.CHAT} ")
        }

    if shape(after) <= shape(before):
        return None
    return Finding(
        "L2", "model: new finish reasons", "", after[0]["trace"], ""
    )


def attribute(traces: list[Trace]) -> list[Finding]:
    before = [t for t in traces if t["phase"] == "before"]
    after = [t for t in traces if t["phase"] == "after"]
    checks = (provider, model, retrieval)
    return [f for check in checks if (f := check(before, after))]


def load(path: Path) -> list[Trace]:
    traces: list[Trace] = json.loads(path.read_text())
    return traces


def report(traces: list[Trace]) -> list[str]:
    interactive = [
        t for t in traces if t["request_class"] == "interactive"
    ]
    lines = ["first chunks of interactive answers, both hours:"]
    s = spread((t["first_chunk_s"] for t in interactive), THRESHOLD_S)
    lines.append(
        f"  mean {s.mean:.2f} s, p50 {s.p50:.2f} s,"
        f" p95 {s.p95:.2f} s; {s.over} of {s.n} over {THRESHOLD_S} s"
    )
    for f in attribute(traces):
        lines += [
            f"{f.layer} {f.what}",
            f"   {f.evidence}",
            f"   exemplar {f.exemplar}",
        ]
    return lines
