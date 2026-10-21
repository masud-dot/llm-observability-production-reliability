"""Appendix A: the contract reference and the retention settings
cannot drift from the code and the configurations."""

import re
from pathlib import Path

import yaml

from wrenholt.privacy.contract import FIELDS, RETENTION_DAYS
from wrenholt.telemetry import conventions as c
from wrenholt.telemetry import reference as ref

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "deploy" / "compose"
STAND_INS = {"answer"}  # the fixture's stand-in for the API's span


def pattern(name: str) -> re.Pattern[str]:
    return re.compile(
        re.sub(r"\\\{[^}]+\\\}", r"\\S+", re.escape(name))
    )


def test_the_committed_reference_is_current() -> None:
    assert ref.REFERENCE.read_text() == ref.render()


def test_every_emitted_span_is_listed(
    seen: dict[str, set[str]],
) -> None:
    patterns = [pattern(s.name) for s in ref.SPANS]
    names = seen["spans"] - STAND_INS
    assert names
    assert [n for n in names if not any(
        p.fullmatch(n) for p in patterns)] == []  # fmt: skip


def test_every_listed_span_is_in_its_module() -> None:
    for s in ref.SPANS:
        assert s.code in (ROOT / s.module).read_text(), s.name


def test_events_are_listed(seen: dict[str, set[str]]) -> None:
    assert seen["events"] == {name for name, _, _ in ref.EVENTS}


def test_retention_matches_the_contract() -> None:
    days = RETENTION_DAYS
    prom = yaml.safe_load(
        (CFG / "prometheus/prometheus.yml").read_text()
    )
    assert prom["storage"]["tsdb"]["retention"]["time"] == (
        f"{days['metrics']}d"
    )
    tempo = yaml.safe_load((CFG / "tempo/tempo.yaml").read_text())
    hours = f"{days['traces'] * 24}h"
    scheduler = tempo["backend_scheduler"]["provider"]["compaction"]
    assert scheduler["compaction"]["block_retention"] == hours
    worker = tempo["backend_worker"]["compaction"]
    assert worker["block_retention"] == hours
    loki = yaml.safe_load((CFG / "loki/loki.yaml").read_text())
    assert loki["compactor"]["retention_enabled"] is True
    assert loki["limits_config"]["retention_period"] == (
        f"{days['logs'] * 24}h"
    )
    assert (days["metrics"], days["traces"], days["logs"]) == (
        35,
        14,
        14,
    )


def test_the_counts_the_appendix_states() -> None:
    rows = {k: v.count("\n") - 1 for k, v in ref.tables().items()}
    assert rows == {
        "resource": 7, "spans": 9, "events": 4, "attributes": 104,
        "metrics": 22, "never": 10, "handling": 5, "retention": 3,
        "sampling": 8,
    }  # fmt: skip
    # 21 metrics and a total of 1,997 series; no identifier is a label
    assert sum(b.series for b in c.BUDGET) == 1997
    on = ref.labels()
    assert [k for k in on if FIELDS[k].value == "identifier"] == []
