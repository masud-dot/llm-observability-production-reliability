"""Dashboard-query lint against the conventions module."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from wrenholt.telemetry import conventions as c
from wrenholt.telemetry import drift, promnames

ROOT = Path(__file__).resolve().parents[2]
GRAFANA = ROOT / "deploy" / "compose" / "grafana" / "provisioning"
BOARDS = sorted((GRAFANA / "dashboards").glob("*.json"))
PROMTOOL = shutil.which("promtool")
Emitted = tuple[set[str], list[tuple[str, str, str, set[str]]]]


def test_dashboard_queries_use_registered_names() -> None:
    assert BOARDS
    assert drift.lint_dashboards(BOARDS, c.REGISTRY) == []


def test_dashboard_names_come_from_a_real_run(
    emitted: Emitted,
) -> None:
    series, labels = drift.produced(emitted[1])
    for board in BOARDS:
        for expr in drift.prometheus_queries(board):
            used, grouped = drift.promql_names(expr)
            assert used <= series, expr
            assert grouped <= labels, expr


def test_dashboards_use_provisioned_datasources() -> None:
    sources = yaml.safe_load(
        (GRAFANA / "datasources" / "datasources.yaml").read_text()
    )
    uids = {d["uid"] for d in sources["datasources"]}
    for board in BOARDS:
        panels = yaml.safe_load(board.read_text())["panels"]
        used = {p["datasource"]["uid"] for p in panels}
        used |= {
            t["datasource"]["uid"]
            for p in panels
            for t in p["targets"]
        }
        assert used <= uids, board.name


@pytest.mark.parametrize(
    ("name", "instrument", "unit", "expected"),
    [  # as Prometheus stored them in Chapter 4's native run
        (c.ATTEMPTS, "counter", "{attempt}",
         {"wrenholt_gateway_attempts_total"}),
        (c.OPERATION_DURATION, "histogram", "s",
         {"gen_ai_client_operation_duration_seconds_bucket",
          "gen_ai_client_operation_duration_seconds_sum",
          "gen_ai_client_operation_duration_seconds_count"}),
    ],
)  # fmt: skip
def test_prometheus_names(
    name: str, instrument: str, unit: str, expected: set[str]
) -> None:
    assert promnames.series(name, instrument, unit) == expected


def test_prometheus_labels() -> None:
    assert promnames.label(c.ERROR_TYPE) == "error_type"
    assert promnames.label(c.PROVIDER_NAME) == "gen_ai_provider_name"


@pytest.mark.skipif(PROMTOOL is None, reason="no promtool on PATH")
def test_dashboard_promql_parses(tmp_path: Path) -> None:
    exprs = [e for b in BOARDS for e in drift.prometheus_queries(b)]
    rules = [
        {"record": f"check:{i}", "expr": e}
        for i, e in enumerate(exprs)
    ]
    path = tmp_path / "rules.yaml"
    path.write_text(
        yaml.safe_dump({"groups": [{"name": "d", "rules": rules}]})
    )
    run = [str(PROMTOOL), "check", "rules", str(path)]
    subprocess.run(run, check=True, capture_output=True)


def silent_test() -> dict[str, object]:
    """Two attempt series, neither with a provider label."""
    metric = "wrenholt_gateway_attempts_total"
    series = [
        {
            "series": f'{metric}{{error_type="{e}"}}',
            "values": "0+1x10",
        }
        for e in ("rate_limited", "auth")
    ]
    check = {
        "expr": f"sum by (gen_ai_provider_name) ({metric})",
        "eval_time": "5m",
        "exp_samples": [{"labels": "{}", "value": 10}],
    }
    test = {"interval": "1m", "input_series": series}
    test["promql_expr_test"] = [check]
    return {"tests": [test]}


@pytest.mark.skipif(PROMTOOL is None, reason="no promtool on PATH")
def test_grouping_by_a_missing_label_fails_silently(
    tmp_path: Path,
) -> None:
    """Prometheus still answers, with one group and no label."""
    path = tmp_path / "silent.yaml"
    path.write_text(yaml.safe_dump(silent_test()))
    run = [str(PROMTOOL), "test", "rules", str(path)]
    subprocess.run(run, check=True, capture_output=True)
