"""Prometheus recording rules from the SLO file (Chapter 12).

    uv run python scripts/slo_rules.py

For every SLO counted in Prometheus the rules record its error ratio
over Chapter 14's alert windows and over the SLO window, and its
valid events in the last hour and the last 6 hours; where there is
an objective, also the objective and the share of the budget left.
Metric and label names come from the conventions module, as
Prometheus stores them, so a rename there reaches the rules.
"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from wrenholt.slo.objectives import Objectives, Slo, load_objectives
from wrenholt.telemetry import conventions as c
from wrenholt.telemetry.promnames import label, series

ALERT_WINDOWS = ("5m", "30m", "1h", "6h", "3d")  # Chapter 14
VALID_WINDOWS = ("1h", "6h")  # Chapter 14: a page's long windows
RULES_PATH = (
    Path(__file__).resolve().parents[3]
    / "deploy/compose/prometheus/rules/slo.rules.yaml"
)
HEADER = (
    "# Generated from src/wrenholt/slo/objectives.yaml by\n"
    "# scripts/slo_rules.py. Do not edit by hand.\n"
)


def promname(metric: str, part: str = "") -> str:
    """The series a registered metric becomes, or one of a
    histogram's three: bucket, sum or count."""
    n = next(n for n in c.REGISTRY if n.name == metric)
    names = series(n.name, n.instrument, n.unit)
    return next(s for s in names if s.endswith(part))


def le(threshold: float) -> str:
    """A boundary as Prometheus stores it: 4.0 becomes "4"."""
    return format(Decimal(str(threshold)).normalize(), "f")


def match(**labels: str) -> str:
    pairs = (f'{label(k)}="{v}"' for k, v in labels.items())
    return "{" + ",".join(pairs) + "}"


@dataclass(frozen=True)
class Counting:
    valid: str  # a selector
    bad: str = ""  # a selector of bad events, or
    good: str = ""  # one of good events, when bad has none


def counting(s: Slo) -> Counting:
    if s.counted_by == "events":
        events = promname(c.SLO_EVENTS)
        valid = events + match(**{c.SLO_SLI: s.sli_id})
        bad = {c.SLO_SLI: s.sli_id, c.SLO_GOOD: "false"}
        return Counting(valid, bad=events + match(**bad))
    if s.counted_by == "first_chunk":
        assert s.request_class and s.threshold_s
        cls = {c.REQUEST_CLASS: s.request_class}
        good = match(**cls, le=le(s.threshold_s))
        return Counting(
            promname(c.ANSWER_FIRST_CHUNK, "count") + match(**cls),
            good=promname(c.ANSWER_FIRST_CHUNK, "bucket") + good,
        )
    if s.counted_by == "refund_calls":
        calls = promname(c.TOOL_DURATION, "count")
        refund = {c.TOOL_NAME: "issue_refund"}
        bad = {**refund, c.ERROR_TYPE: "invalid_arguments"}
        return Counting(calls + match(**refund), calls + match(**bad))
    if s.counted_by == "evaluation":  # Chapter 13
        assert s.bad_label
        results = promname(c.EVALUATION_RESULTS)
        evaluated = {c.EVALUATION_NAME: s.sli_id}
        bad = {**evaluated, c.EVALUATION_LABEL: s.bad_label}
        return Counting(
            results + match(**evaluated), bad=results + match(**bad)
        )
    if s.counted_by == "attempts":
        attempts = promname(c.ATTEMPTS)
        failed = "{" + label(c.ERROR_TYPE) + '!=""}'
        return Counting(attempts, bad=attempts + failed)
    raise ValueError(f"{s.slo} is not counted in Prometheus")


def error_ratio(k: Counting, window: str) -> str:
    """Bad over valid. A bad series that does not exist yet counts
    as zero, and so does a good one, which makes a misspelt bucket
    boundary count every event bad rather than none. A window
    without valid events records nothing."""
    valid = f"sum(rate({k.valid}[{window}]))"
    if k.bad:
        bad = f"sum(rate({k.bad}[{window}]))"
    else:
        good = f"(sum(rate({k.good}[{window}])) or vector(0))"
        bad = f"({valid} - {good})"
    return f"({bad} or vector(0)) / ({valid} > 0)"


def rules_for(s: Slo, window: str) -> list[dict[str, Any]]:
    k = counting(s)
    labels = {"slo": s.slo, "sli": s.sli_id, "layer": s.layer}
    rules = [
        {
            "record": f"slo:sli_error:ratio_rate{w}",
            "expr": error_ratio(k, w),
            "labels": dict(labels),
        }
        for w in (*ALERT_WINDOWS, window)
    ]
    rules += [
        {
            "record": f"slo:valid_events:increase{w}",
            "expr": f"sum(increase({k.valid}[{w}]))",
            "labels": dict(labels),
        }
        for w in VALID_WINDOWS
    ]
    if s.objective is not None:
        ratio = f'slo:sli_error:ratio_rate{window}{{slo="{s.slo}"}}'
        rules += [
            {
                "record": "slo:objective:ratio",
                "expr": f"vector({s.objective})",
                "labels": dict(labels),
            },
            {
                "record": "slo:error_budget_remaining:ratio",
                "expr": f"1 - {ratio} / {s.budget}",
                "labels": dict(labels),
            },
        ]
    return rules


def generate(objectives: Objectives | None = None) -> dict[str, Any]:
    slos = objectives or load_objectives()
    return {
        "groups": [
            {
                "name": f"slo-{s.slo}",
                "interval": "1m",
                "rules": rules_for(s, slos.window),
            }
            for s in slos.objectives
        ]
    }


def render(objectives: Objectives | None = None) -> str:
    body = yaml.safe_dump(
        generate(objectives), sort_keys=False, width=1000
    )
    return HEADER + body


def recorded() -> dict[str, set[str]]:
    """Each recorded series and its labels, for the dashboard lint."""
    return {
        r["record"]: set(r["labels"])
        for g in generate()["groups"]
        for r in g["rules"]
    }
