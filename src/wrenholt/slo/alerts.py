"""Burn-rate alerts from the SLO file (Chapter 14).

    uv run python scripts/slo_alerts.py

Every SLO with an objective gets the SRE Workbook's multiwindow,
multi-burn-rate alerts over Chapter 12's recorded error ratios. A
tier fires when its long window and its short window, one twelfth as
long, both burn the budget faster than the tier's rate. Grafana
evaluates the alerts from a file it provisions and sends them to the
incident webhook; the same expressions are written as Prometheus
alerting rules, which promtool tests on synthetic series.
"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml

from wrenholt.slo.errorbudget import WINDOW_HOURS, spent
from wrenholt.slo.objectives import Objectives, Slo, load_objectives

ROOT = Path(__file__).resolve().parents[3]
GRAFANA = "deploy/compose/grafana/provisioning/alerting"
GRAFANA_PATH = ROOT / GRAFANA / "slo-alerts.yaml"
PROMETHEUS_PATH = ROOT / "tests/slo/slo_alerts.rules.yaml"
RUNBOOKS = "docs/runbooks.md"
HEADER = (
    "# Generated from src/wrenholt/slo/objectives.yaml by\n"
    "# scripts/slo_alerts.py. Do not edit by hand.\n"
)
MIN_BAD = 2  # one bad event never pages
WEBHOOK = "$WRENHOLT_INCIDENT_WEBHOOK"  # Grafana fills it in
RECEIVER = "incident-webhook"

Severity = Literal["page", "ticket"]


@dataclass(frozen=True)
class Tier:
    severity: Severity
    long: str
    short: str
    burn: Decimal
    long_minutes: int


TIERS = (
    Tier("page", "1h", "5m", Decimal("14.4"), 60),
    Tier("page", "6h", "30m", Decimal(6), 6 * 60),
    Tier("ticket", "3d", "6h", Decimal(1), 3 * 24 * 60),
)


def tiers_for(s: Slo) -> tuple[Tier, ...]:
    """Pages for what customers feel within the hour, L1 and L2;
    tickets for content and cost, L3 and L4, and for evaluation
    results, which arrive late and few (Chapter 13)."""
    if s.objective is None:
        return ()
    if s.layer in ("L1", "L2") and s.counted_by != "evaluation":
        return TIERS
    return TIERS[-1:]


def number(d: Decimal) -> str:
    return format(d.normalize(), "f")


def ratio(s: Slo, window: str) -> str:
    return f'slo:sli_error:ratio_rate{window}{{slo="{s.slo}"}}'


def expression(s: Slo, t: Tier) -> str:
    """Both windows over the tier's threshold. A page also needs
    more than one bad event in its long window: the ratio times
    the valid events there."""
    limit = number(t.burn * s.budget)
    lines = [
        ratio(s, t.long),
        f"  > {limit}",
        f"and {ratio(s, t.short)}",
        f"  > {limit}",
    ]
    if t.severity == "page":
        valid = f'slo:valid_events:increase{t.long}{{slo="{s.slo}"}}'
        lines += [
            f"and {ratio(s, t.long)}",
            f"  * {valid}",
            f"  >= {MIN_BAD}",
        ]
    return "\n".join(lines)


def alertname(s: Slo, t: Tier) -> str:
    return f"slo_burn_{s.slo}_{t.severity}_{t.long}"


def labels(s: Slo, t: Tier) -> dict[str, str]:
    assert s.owner, s.slo
    return {
        "severity": t.severity,
        "slo": s.slo,
        "layer": s.layer,
        "owner": s.owner,
        "window": t.long,
    }


def annotations(s: Slo, t: Tier) -> dict[str, str]:
    burn = number(t.burn)
    return {
        "summary": (
            f"{s.slo} is spending its error budget {burn} times"
            f" too fast over {t.long} and {t.short}"
        ),
        "runbook_url": f"{RUNBOOKS}#{s.slo}",
    }


def grafana_rule(s: Slo, t: Tier) -> dict[str, Any]:
    """One Grafana-managed rule: the expression as an instant query,
    firing for any result above zero. No data means no burn."""
    query = {
        "refId": "A",
        "expr": expression(s, t),
        "instant": True,
        "range": False,
        "intervalMs": 60000,
        "maxDataPoints": 43200,
    }
    over_zero = {
        "refId": "B",
        "type": "threshold",
        "expression": "A",
        "conditions": [{"evaluator": {"type": "gt", "params": [0]}}],
        "datasource": {"type": "__expr__", "uid": "__expr__"},
    }
    return {
        "uid": alertname(s, t),
        "title": alertname(s, t),
        "condition": "B",
        "data": [
            {
                "refId": "A",
                "relativeTimeRange": {"from": 600, "to": 0},
                "datasourceUid": "prometheus",
                "model": query,
            },
            {
                "refId": "B",
                "datasourceUid": "__expr__",
                "model": over_zero,
            },
        ],
        "noDataState": "OK",
        "execErrState": "Error",
        "for": "0s",
        "labels": labels(s, t),
        "annotations": annotations(s, t),
    }


def routes() -> list[dict[str, Any]]:
    """A page is sent within a minute and repeated hourly; a ticket
    waits five minutes to gather and is repeated daily."""
    return [
        {
            "receiver": RECEIVER,
            "object_matchers": [["severity", "=", "page"]],
            "group_wait": "30s",
            "group_interval": "5m",
            "repeat_interval": "1h",
        },
        {
            "receiver": RECEIVER,
            "object_matchers": [["severity", "=", "ticket"]],
            "group_wait": "5m",
            "group_interval": "1h",
            "repeat_interval": "24h",
        },
    ]


def grafana(objectives: Objectives | None = None) -> dict[str, Any]:
    slos = objectives or load_objectives()
    return {
        "apiVersion": 1,
        "contactPoints": [
            {
                "orgId": 1,
                "name": RECEIVER,
                "receivers": [
                    {
                        "uid": "incident_webhook",
                        "type": "webhook",
                        "settings": {"url": WEBHOOK},
                    }
                ],
            }
        ],
        "policies": [
            {
                "orgId": 1,
                "receiver": RECEIVER,
                "group_by": ["slo", "severity"],
                "routes": routes(),
            }
        ],
        "groups": [
            {
                "orgId": 1,
                "name": f"slo-{s.slo}",
                "folder": "SLO alerts",
                "interval": "1m",
                "rules": [grafana_rule(s, t) for t in tiers_for(s)],
            }
            for s in slos.objectives
            if tiers_for(s)
        ],
    }


def prometheus(
    objectives: Objectives | None = None,
) -> dict[str, Any]:
    """The same expressions and labels as Prometheus alerting rules,
    for promtool; the annotations live in Grafana's file."""
    slos = objectives or load_objectives()
    return {
        "groups": [
            {
                "name": f"slo-alerts-{s.slo}",
                "interval": "1m",
                "rules": [
                    {
                        "alert": alertname(s, t),
                        "expr": expression(s, t),
                        "labels": labels(s, t),
                    }
                    for t in tiers_for(s)
                ],
            }
            for s in slos.objectives
            if tiers_for(s)
        ]
    }


class Dumper(yaml.SafeDumper):
    """Writes a string with line breaks as a literal block, so each
    expression keeps one condition to a line."""


def _string(dumper: yaml.SafeDumper, data: str) -> yaml.Node:
    style = "|" if "\n" in data else None
    tag = "tag:yaml.org,2002:str"
    return dumper.represent_scalar(tag, data, style=style)


Dumper.add_representer(str, _string)


def render(document: dict[str, Any]) -> str:
    body = yaml.dump(
        document, Dumper=Dumper, sort_keys=False, width=60
    )
    return HEADER + body


def detection_minutes(
    s: Slo, t: Tier, error_ratio: Decimal
) -> Decimal | None:
    """The Workbook's detection time: how long an error ratio must
    last for the long window to cross the tier's threshold. None
    when the ratio never gets there."""
    if error_ratio <= t.burn * s.budget:
        return None
    return s.budget / error_ratio * t.long_minutes * t.burn


def spent_at_threshold(
    t: Tier, window_hours: Decimal = WINDOW_HOURS
) -> Decimal:
    """The share of the SLO window's budget that a burn at the
    tier's rate spends over its long window."""
    return spent(t.burn, Decimal(t.long_minutes) / 60, window_hours)
