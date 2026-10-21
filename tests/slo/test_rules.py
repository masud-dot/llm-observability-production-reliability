"""The rule generator (Chapter 12)."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from wrenholt.slo import rules

ROOT = Path(__file__).resolve().parents[2]
PROMETHEUS = ROOT / "deploy" / "compose" / "prometheus"
PROMTOOL = shutil.which("promtool")
TESTS = Path(__file__).with_name("slo_rules.test.yaml")
WINDOWS = [
    f"slo:sli_error:ratio_rate{w}" for w in rules.ALERT_WINDOWS
]


def records() -> dict[str, list[str]]:
    return {
        g["name"]: [r["record"] for r in g["rules"]]
        for g in rules.generate()["groups"]
    }


def expr(group: str, record: str) -> str:
    return next(
        str(r["expr"])
        for g in rules.generate()["groups"]
        if g["name"] == group
        for r in g["rules"]
        if r["record"] == record
    )


def test_the_committed_rules_are_the_generated_ones() -> None:
    assert rules.RULES_PATH.read_text() == rules.render()


def test_each_slo_gets_its_rules() -> None:
    found = records()
    # Chapter 13: groundedness, counted from evaluation results
    assert found["slo-groundedness"][-2:] == [
        "slo:objective:ratio",
        "slo:error_budget_remaining:ratio",
    ]
    window = [*WINDOWS, "slo:sli_error:ratio_rate28d"]
    measured = [
        *window,
        "slo:valid_events:increase1h",
        "slo:valid_events:increase6h",  # Chapter 14: pages
    ]
    budgeted = [
        *measured,
        "slo:objective:ratio",
        "slo:error_budget_remaining:ratio",
    ]
    assert found["slo-availability"] == budgeted
    assert found["slo-resolution"] == measured  # no objective
    assert len(found) == 10
    total = sum(len(r) for r in found.values())
    assert total == 8 * 10 + 2 * 8 == 96


def test_thresholds_are_written_as_prometheus_stores_them() -> None:
    assert [rules.le(x) for x in (4.0, 2.5, 10.0)] == [
        "4",
        "2.5",
        "10",
    ]
    critical = expr("slo-ttfc_critical_action", WINDOWS[0])
    assert 'le="4"}' in critical and "4.0" not in critical


def test_the_rules_count_bad_events_and_divide_by_the_budget() -> (
    None
):
    assert expr("slo-decision_validity", WINDOWS[2]) == (
        "(sum(rate(gen_ai_execute_tool_duration_seconds_count"
        '{gen_ai_tool_name="issue_refund",'
        'error_type="invalid_arguments"}[1h])) or vector(0)) / '
        "(sum(rate(gen_ai_execute_tool_duration_seconds_count"
        '{gen_ai_tool_name="issue_refund"}[1h])) > 0)'
    )
    assert expr(
        "slo-availability", "slo:error_budget_remaining:ratio"
    ) == (
        '1 - slo:sli_error:ratio_rate28d{slo="availability"} / 0.001'
    )


def test_prometheus_loads_the_rules_and_keeps_the_window() -> None:
    config = yaml.safe_load(
        (PROMETHEUS / "prometheus.yml").read_text()
    )
    assert config["rule_files"] == ["rules/slo.rules.yaml"]
    # the default 15 days would cut the 28-day window short
    assert config["storage"]["tsdb"]["retention"]["time"] == "35d"
    compose = yaml.safe_load(
        (
            ROOT / "deploy" / "compose" / "docker-compose.yml"
        ).read_text()
    )
    mounts = compose["services"]["prometheus"]["volumes"]
    assert "./prometheus/rules:/etc/prometheus/rules:ro" in mounts


@pytest.mark.skipif(PROMTOOL is None, reason="no promtool on PATH")
def test_promtool_checks_and_unit_tests_the_rules() -> None:
    assert PROMTOOL is not None
    subprocess.run(
        [PROMTOOL, "check", "rules", str(rules.RULES_PATH)],
        check=True,
        capture_output=True,
    )
    tested = subprocess.run(
        [PROMTOOL, "test", "rules", str(TESTS)],
        capture_output=True,
        text=True,
    )
    assert tested.returncode == 0, tested.stdout + tested.stderr
