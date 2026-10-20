"""Release gates, the canary and the self-assessment (Chapter 20).

The workflow is parsed here, not run: GitHub Actions does not run
in these tests.
"""

import math
import subprocess
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from wrenholt import gates as g
from wrenholt.evaluation.drift import Rate
from wrenholt.labs import gate_lab
from wrenholt.labs.eval_lab import RATE, hours_to
from wrenholt.labs.fs10_lab import V3, run_lab
from wrenholt.labs.fs12_lab import HOUR
from wrenholt.maturity import Answer, assess, level
from wrenholt.orchestrator.prompts import SUPPORT
from wrenholt.slo.errorbudget import lasts_hours

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = "src/wrenholt/orchestrator/prompts.py"


def test_changes_are_classified_by_path() -> None:
    assert g.kinds([PROMPTS]) == {"prompt", "code"}
    assert g.gates([PROMPTS]) == ["contract", "drift", "evaluation"]
    assert g.gates(["src/wrenholt/gateway/prices.yaml"]) == [
        "evaluation"
    ]
    assert g.kinds(["src/wrenholt/api/app.py"]) == {"model", "code"}
    assert g.kinds(["src/wrenholt/rag/index.py"]) == {"index", "code"}
    otelcol = "deploy/compose/otelcol/config.yaml"
    assert g.gates([otelcol]) == ["contract", "drift"]
    assert g.gates(["README.md", "docs/runbooks.md"]) == []


def test_fs10_is_blocked_by_the_evaluation_gate() -> None:
    assert HOUR.total() == 120
    assert g.budget("not_refused") == pytest.approx(0.005)
    v1, v3 = gate_lab.suite(SUPPORT), gate_lab.suite(V3)
    assert v1.passed
    assert v1.reason == "0.0% of the mix refused, budget 0.5%"
    assert not v3.passed
    assert v3.reason == (
        "25.0% of the mix refused, budget 0.5%: order_status"
    )
    assert HOUR["order_status"] == 30


def test_evaluation_gate_weighs_cases_by_the_mix() -> None:
    mix = {"a": 1, "b": 199}
    assert g.evaluation({"a": True, "b": False}, mix, 0.005).passed
    heavier = {"a": 2, "b": 198}
    assert not g.evaluation({"a": True}, heavier, 0.005).passed


def test_canary_decisions() -> None:
    errors = g.budget("availability")
    assert errors == pytest.approx(0.001)
    few = Rate(0, 29, "errors")
    assert g.decide(Rate(0, 270, "errors"), few, errors) == g.WAIT
    same = Rate(0, 30, "errors")
    assert g.decide(Rate(0, 270, "errors"), same, errors) == g.PROMOTE
    moved = Rate(30, 30, "m")
    assert g.decide(Rate(0, 270, "m"), moved, 0.0) == g.ROLL_BACK
    # Better than the control never rolls back: the test is one-sided.
    assert g.decide(Rate(10, 100, "e"), Rate(0, 100, "e"), 0) == (
        g.PROMOTE
    )
    # Significant, but inside the budget: the objective absorbs it.
    base, now = Rate(0, 10_000, "e"), Rate(9, 10_000, "e")
    pooled = 9 / 20_000
    z = 0.0009 / math.sqrt(pooled * (1 - pooled) * 2 / 10_000)
    assert z == pytest.approx(3.0, abs=0.001)
    assert g.decide(base, now, errors) == g.PROMOTE
    # No errors in n events: the 95 per cent bound is about 3/n, so
    # 3,000 clean events to show 99.9 per cent; 250 hours at 12/h.
    assert round(3 / errors) == 3000
    assert 3000 / 12 == 250


def test_fs11_is_caught_by_the_canary_with_the_pin() -> None:
    split = gate_lab.traffic()
    control, canary = split[gate_lab.CONTROL], split[gate_lab.CANARY]
    assert (len(control), len(canary)) == (270, 30)
    calls = g.canary(control, canary)
    found = [(c.signal, c.canary.hits, c.decision) for c in calls]
    assert found == [
        ("errors", 0, g.PROMOTE),
        ("model_mismatch", 30, g.ROLL_BACK),
    ]
    assert g.verdict(calls[:1]) == g.PROMOTE  # errors alone
    assert g.verdict(calls) == g.ROLL_BACK
    # 12 canary answers an hour: 30 of them take three hours.
    assert HOUR.total() / 10 == 12
    assert hours_to(12) == 3
    assert RATE == 0.1


def test_verdict_order() -> None:
    def call(d: str) -> g.Call:
        r = Rate(0, 30, "e")
        return g.Call("e", r, r, d)

    assert g.verdict([call(g.WAIT), call(g.ROLL_BACK)]) == g.ROLL_BACK
    assert g.verdict([call(g.PROMOTE), call(g.WAIT)]) == g.WAIT
    assert g.verdict([call(g.PROMOTE)]) == g.PROMOTE


def test_budget_gate_follows_the_policy() -> None:
    reasons = [
        g.budget_gate(gate_lab.SPENDS, team, labels)
        for team, labels in gate_lab.CHANGES
    ]
    assert [v.passed for v in reasons] == [False, True, True]
    assert reasons[0].reason == (
        "assistant: not_refused exhausted; release held"
    )
    assert reasons[1].reason == (
        "assistant: not_refused exhausted; fix ships"
    )
    assert reasons[2].reason == (
        "platform: availability spent by an outside cause; no freeze"
    )
    help_centre = g.budget_gate(gate_lab.SPENDS, "help-centre", set())
    assert help_centre.reason == "help-centre: no budget exhausted"
    left = [g.Spend("x", "t", Decimal("0.01"))]
    assert g.budget_gate(left, "t", set()).passed


def test_ci_runs_only_the_gates_needed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ran: list[tuple[str, ...]] = []

    def fake(cmd: tuple[str, ...], check: bool) -> Any:
        ran.append(cmd)
        failed = cmd[-1] == "evaluate"
        return subprocess.CompletedProcess(cmd, int(failed))

    monkeypatch.setattr(subprocess, "run", fake)
    monkeypatch.setattr(g, "changed", lambda base: [PROMPTS])
    assert g.ci("origin/main") == 1
    assert ran == [g.COMMANDS[x] for x in g.ORDER]
    assert "evaluation: FAILED" in capsys.readouterr().out
    ran.clear()
    monkeypatch.setattr(g, "changed", lambda base: ["README.md"])
    assert g.ci("origin/main") == 0
    assert ran == []


def test_workflow_runs_the_gates_on_pull_requests() -> None:
    path = ROOT / ".github/workflows/gates.yml"
    flow = yaml.safe_load(path.read_text())
    assert "pull_request" in flow[True]  # YAML 1.1 reads "on" as True
    assert flow["permissions"] == {"contents": "read"}
    (checkout, run) = flow["jobs"]["gates"]["steps"]
    assert checkout["with"] == {"fetch-depth": 0}
    assert "scripts/gates.py ci --base" in run["run"]
    assert "--group lab" in run["run"]
    # Phase 3: the contract gate's Collector tests need the binary.
    assert "scripts/fetch_collector.sh" in run["run"]


def test_self_assessment() -> None:
    answers = assess()
    assert [a.stage for a in answers] == [
        "Observe", "Measure", "Evaluate",
        "Diagnose", "Recover", "Improve",
    ]  # fmt: skip
    assert all(a.met for a in answers)
    assert level(answers) == 6
    assert answers[1].evidence == "8 objectives, each owned"
    held = answers[4].evidence
    assert held == "18 of 18 experiments held or detected"
    gap = [Answer("a", "", True), Answer("b", "", False),
           Answer("c", "", True)]  # fmt: skip
    assert level(gap) == 1


def test_fs10_exposure_before_each_check() -> None:
    # Figure 20.2: refused answers before FS-10 is caught.
    r = run_lab()
    per_hour = r.refusals(r.after)
    assert per_hour == 30
    full, _ = r.flagged(1.0)
    canary, _ = r.flagged(0.1)
    assert (full, canary) == (3, 25)
    assert full * per_hour == 90
    assert canary * per_hour / 10 == 75
    # 25 per cent refused burns a 0.5 per cent budget 50 times over.
    burn = Decimal("0.25") / Decimal("0.005")
    assert burn == 50
    assert lasts_hours(burn) == Decimal("13.44")
