"""Diagnosis (Chapter 15): the walkthrough on the recorded hour of
FS-08 behind FS-02, the vault's gate and the bundle replay."""

import importlib.util
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from wrenholt import diagnosis as d
from wrenholt.labs import diagnosis_lab as lab
from wrenholt.privacy.vault import Reader
from wrenholt.telemetry import conventions as c

TRACES = d.load(lab.FIXTURE)
AFTER = [t for t in TRACES if t["phase"] == "after"]
SAM = Reader("sam", "investigator", "wrenholt")


def test_the_fixture_holds_no_content() -> None:
    names = {n.name for n in c.REGISTRY}
    captured = json.loads(lab.CAPTURED.read_text())
    text = lab.FIXTURE.read_text()
    for t in TRACES:
        for s in t["spans"]:
            assert set(s["attributes"]) <= names - set(c.CONTENT)
    for body in captured.values():
        assert body["question"] not in text
    assert len(TRACES) == 24 and set(captured) == {
        t["trace"] for t in TRACES
    }


def test_the_mean_hides_two_modes() -> None:
    interactive = [
        t for t in TRACES if t["request_class"] == "interactive"
    ]
    s = d.spread((t["first_chunk_s"] for t in interactive), 2.5)
    assert (s.n, s.mean, s.p50, s.p95, s.over) == (
        18,
        1.7,
        0.4,
        3.0,
        9,
    )
    assert s.mean < d.THRESHOLD_S  # the mean says all is well
    modes = {t["phase"]: t["first_chunk_s"] for t in interactive}
    assert modes == {"before": 0.4, "after": 3.0}


def test_the_layer_comes_first() -> None:
    found = d.attribute(TRACES)
    assert [f.layer for f in found] == ["L1", "L3"]
    l1, l3 = found
    assert l1.what.endswith("first chunk median +2.60 s")
    assert l1.evidence.endswith("+0.00 s")
    assert l3.what == "retrieval: 12 of 12 returned nothing"
    assert l3.evidence == (
        "index built with wrenholt-embed-2,"
        " questions with wrenholt-embed-1"
    )
    assert {l1.exemplar, l3.exemplar} <= {t["trace"] for t in AFTER}
    assert 'span.wrenholt.index.embedder = "wrenholt-embed-2"' in (
        l3.query
    )
    assert "time_to_first_chunk_seconds_bucket" in l1.query


def test_fixing_the_provider_leaves_the_retrieval_fault() -> None:
    healed = [
        {**t, "first_chunk_s": 0.4} if t["phase"] == "after" else t
        for t in TRACES
    ]
    assert [f.layer for f in d.attribute(healed)] == ["L3"]


def test_the_vault_gates_the_reproduction() -> None:
    v = lab.vault()
    trace = AFTER[0]["trace"]
    with pytest.raises(PermissionError, match="role or reason"):
        lab.question(v, trace, SAM, "")
    support = replace(SAM, role="support")
    with pytest.raises(PermissionError, match="role or reason"):
        lab.question(v, trace, support, "INC-0042")
    asked = lab.question(v, trace, SAM, "INC-0042: empty retrieval")
    assert asked in lab.HOUR
    log = v.access_log()
    assert [e["outcome"] for e in log][-3:] == [
        "denied: role or reason",
        "denied: role or reason",
        "granted",
    ]
    assert asked not in json.dumps(log)


def test_the_replay_reproduces_retrieval_not_the_brownout() -> None:
    t = AFTER[0]
    asked = lab.question(lab.vault(), t["trace"], SAM, "INC-0042")
    again = lab.replay(t["bundle"], asked)
    assert (again.documents, again.grounded) == (0, False)
    fixed = lab.replay(
        t["bundle"], asked, "45e99498.wrenholt-embed-1"
    )
    assert (fixed.documents, fixed.grounded) == (2, True)
    changed: dict[str, Any] = {**t["bundle"], "prompt_sha256": "0"}
    with pytest.raises(ValueError, match="prompt has changed"):
        lab.replay(changed, asked)


def test_the_cli_walkthrough(
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts/wrenholt_cli.py"
    spec = importlib.util.spec_from_file_location("cli", path)
    assert spec and spec.loader
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    assert cli.main(["diagnose"]) == 0
    out = capsys.readouterr().out
    assert "mean 1.70 s, p50 0.40 s, p95 3.00 s; 9 of 18" in out
    assert max(len(line) for line in out.splitlines()) <= 70
    trace = AFTER[0]["trace"]
    assert cli.main(["replay", trace, "--reader", "sam"]) == 1
    assert "denied: role or reason" in capsys.readouterr().out
