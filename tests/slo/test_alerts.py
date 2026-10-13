"""Burn-rate alerts (Chapter 14): the Workbook's tiers at Wrenholt's
28-day window, which SLOs page, the generated Grafana and Prometheus
files, detection times, and promtool on synthetic series."""

import re
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from wrenholt.slo import alerts, errorbudget
from wrenholt.slo.alerts import TIERS, detection_minutes, tiers_for
from wrenholt.slo.objectives import load_objectives
from wrenholt.slo.rules import recorded

ROOT = Path(__file__).resolve().parents[2]
PROMTOOL = shutil.which("promtool")
SLOS = load_objectives()


def test_the_committed_alerts_are_the_generated_ones() -> None:
    for path, document in (
        (alerts.GRAFANA_PATH, alerts.grafana()),
        (alerts.PROMETHEUS_PATH, alerts.prometheus()),
    ):
        text = path.read_text(encoding="utf-8")
        assert text == alerts.render(document)
        assert yaml.safe_load(text) == document  # literal blocks
        assert max(len(line) for line in text.splitlines()) <= 70


def test_the_workbook_tiers_and_what_they_spend() -> None:
    assert [(t.long, t.short, t.burn) for t in TIERS] == [
        ("1h", "5m", Decimal("14.4")),
        ("6h", "30m", Decimal(6)),
        ("3d", "6h", Decimal(1)),
    ]
    short = {"5m": 5, "30m": 30, "6h": 360}
    for t in TIERS:  # a short window a twelfth of the long one
        assert t.long_minutes == 12 * short[t.short]
    assert errorbudget.lasts_hours(Decimal("14.4")) < 48
    thirty_days = Decimal(30 * 24)
    assert [
        alerts.spent_at_threshold(t, thirty_days) for t in TIERS
    ] == [Decimal("0.02"), Decimal("0.05"), Decimal("0.1")]
    at_28_days = [
        round(alerts.spent_at_threshold(t), 4) for t in TIERS
    ]
    assert at_28_days == [
        Decimal("0.0214"),
        Decimal("0.0536"),
        Decimal("0.1071"),
    ]


def test_what_pages_and_what_opens_a_ticket() -> None:
    kinds = {
        s.slo: [f"{t.severity} {t.long}" for t in tiers_for(s)]
        for s in SLOS.objectives
    }
    both = ["page 1h", "page 6h", "ticket 3d"]
    assert kinds == {
        "availability": both,
        "ttfc_interactive": both,
        "ttfc_critical_action": both,
        "decision_validity": both,
        "not_refused": both,
        "groundedness": ["ticket 3d"],  # evaluation results
        "policy_freshness": ["ticket 3d"],  # L3
        "answer_cost": ["ticket 3d"],  # L4
        "resolution": [],  # no objective
        "provider_attempts": [],
    }
    assert sum(map(len, kinds.values())) == 18


def test_expressions_read_only_recorded_series() -> None:
    names = recorded()
    a = SLOS.get("availability")
    fast = alerts.expression(a, TIERS[0])
    assert fast.splitlines() == [
        'slo:sli_error:ratio_rate1h{slo="availability"}',
        "  > 0.0144",
        'and slo:sli_error:ratio_rate5m{slo="availability"}',
        "  > 0.0144",
        'and slo:sli_error:ratio_rate1h{slo="availability"}',
        '  * slo:valid_events:increase1h{slo="availability"}',
        "  >= 2",
    ]
    limits = {
        s.slo: alerts.expression(s, TIERS[0]).splitlines()[1]
        for s in SLOS.objectives
        if len(tiers_for(s)) == 3
    }
    assert limits["ttfc_interactive"] == "  > 0.144"
    assert limits["not_refused"] == "  > 0.072"
    ticket = alerts.expression(SLOS.get("groundedness"), TIERS[2])
    assert "valid_events" not in ticket  # tickets need no minimum
    for s in SLOS.objectives:
        for t in tiers_for(s):
            used = re.findall(
                r"(slo:[a-z_:0-9]+)\{", alerts.expression(s, t)
            )
            assert used and all(n in names for n in used)


def test_the_grafana_file() -> None:
    doc = alerts.grafana()
    rules = [r for g in doc["groups"] for r in g["rules"]]
    uids = [r["uid"] for r in rules]
    assert len(uids) == len(set(uids)) == 18
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{1,40}", u) for u in uids)
    sources = yaml.safe_load(
        (
            ROOT
            / "deploy/compose/grafana/provisioning/datasources"
            / "datasources.yaml"
        ).read_text()
    )
    assert {"prometheus"} <= {
        d["uid"] for d in sources["datasources"]
    }
    runbooks = (ROOT / alerts.RUNBOOKS).read_text(encoding="utf-8")
    headings = set(re.findall(r"^## (\S+)$", runbooks, re.M))
    for r in rules:
        assert r["condition"] == "B" and r["noDataState"] == "OK"
        assert r["data"][0]["datasourceUid"] == "prometheus"
        assert r["labels"]["severity"] in ("page", "ticket")
        anchor = r["annotations"]["runbook_url"].split("#")[1]
        assert anchor == r["labels"]["slo"] and anchor in headings
    (point,) = doc["contactPoints"]
    assert point["receivers"][0]["settings"] == {
        "url": "$WRENHOLT_INCIDENT_WEBHOOK"
    }
    (policy,) = doc["policies"]
    assert [r["object_matchers"] for r in policy["routes"]] == [
        [["severity", "=", "page"]],
        [["severity", "=", "ticket"]],
    ]
    compose = yaml.safe_load(
        (ROOT / "deploy/compose/docker-compose.yml").read_text()
    )
    grafana = compose["services"]["grafana"]["environment"]
    assert "WRENHOLT_INCIDENT_WEBHOOK" in grafana
    # Section 14.8: a recording interval, a Grafana interval and a
    # page's wait: up to two and a half minutes after the arithmetic.
    seconds = {"1m": 60, "30s": 30}
    recording = {g["interval"] for g in rules_file()["groups"]}
    grafana_groups = {g["interval"] for g in doc["groups"]}
    page_wait = policy["routes"][0]["group_wait"]
    assert recording == grafana_groups == {"1m"}
    assert 2 * seconds["1m"] + seconds[page_wait] == 150


def rules_file() -> dict[str, list[dict[str, str]]]:
    path = ROOT / "deploy/compose/prometheus/rules/slo.rules.yaml"
    loaded: dict[str, list[dict[str, str]]] = yaml.safe_load(
        path.read_text()
    )
    return loaded


def test_the_minimum_changes_one_page_in_the_normal_hour() -> None:
    """Bad events needed to cross each page's threshold at the
    normal hour's volume: 120 answers, 90 interactive, 30 refunds."""
    hour = {
        "availability": 120,
        "ttfc_interactive": 90,
        "ttfc_critical_action": 30,
        "decision_validity": 30,
        "not_refused": 120,
    }
    needed = {}
    for slo, per_hour in hour.items():
        s = SLOS.get(slo)
        needed[slo] = [
            int(t.burn * s.budget * per_hour * t.long_minutes / 60)
            + 1
            for t in TIERS[:2]
        ]
    assert needed == {
        "availability": [2, 5],
        "ttfc_interactive": [13, 33],
        "ttfc_critical_action": [5, 11],
        "decision_validity": [1, 2],  # the minimum makes this 2
        "not_refused": [9, 22],
    }
    assert alerts.MIN_BAD == 2


def test_detection_times_at_a_full_outage() -> None:
    """The Workbook's formula: (1 - SLO) / error ratio x long window
    x burn rate."""
    every = Decimal(1)
    a, ttfc = SLOS.get("availability"), SLOS.get("ttfc_interactive")
    assert [detection_minutes(a, t, every) for t in TIERS] == [
        Decimal("0.864"),
        Decimal("2.16"),
        Decimal("4.32"),
    ]
    fast = detection_minutes(a, TIERS[0], every)
    assert fast is not None and fast * 60 == Decimal("51.84")  # s
    assert [detection_minutes(ttfc, t, every) for t in TIERS] == [
        Decimal("8.64"),
        Decimal("21.6"),
        Decimal("43.2"),
    ]
    # A ratio at or under the threshold never gets there.
    assert detection_minutes(ttfc, TIERS[0], Decimal("0.144")) is None


@pytest.mark.skipif(PROMTOOL is None, reason="no promtool on PATH")
def test_promtool_checks_and_tests_the_alerts() -> None:
    assert PROMTOOL
    subprocess.run(
        [PROMTOOL, "check", "rules", str(alerts.PROMETHEUS_PATH)],
        check=True,
        capture_output=True,
    )
    tested = subprocess.run(
        [PROMTOOL, "test", "rules", "slo_alerts.test.yaml"],
        cwd=ROOT / "tests/slo",
        capture_output=True,
        text=True,
    )
    assert tested.returncode == 0, tested.stdout + tested.stderr
