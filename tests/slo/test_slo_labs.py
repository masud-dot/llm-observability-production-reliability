"""FS-05 and FS-17 over FS-09's normal hour (Chapter 12): every
number in Table 12.3. SIMULATED: mock provider."""

from decimal import Decimal

import pytest

from wrenholt.guardrail import REFUSAL
from wrenholt.labs import fs05_lab, fs17_lab, slo_lab
from wrenholt.slo import errorbudget

NORMAL_GOOD = {
    "availability": 120,
    "ttfc_interactive": 90,
    "ttfc_critical_action": 30,
    "decision_validity": 30,
    "not_refused": 120,
    "policy_freshness": 120,
    "answer_cost": 120,
    "resolution": 114,
}


@pytest.fixture(scope="module")
def normal() -> slo_lab.Hour:
    return slo_lab.run()


def same(a: slo_lab.Hour, b: slo_lab.Hour, slo: str) -> bool:
    return (a.good[slo], a.valid[slo]) == (b.good[slo], b.valid[slo])


def test_the_normal_hour(normal: slo_lab.Hour) -> None:
    assert dict(normal.good) == NORMAL_GOOD
    assert normal.valid["resolution"] == 120
    assert all(
        normal.valid[s] == n
        for s, n in NORMAL_GOOD.items()
        if s != "resolution"
    )
    assert round(normal.per_resolved, 7) == Decimal("0.0001601")


def test_fs05(normal: slo_lab.Hour) -> None:
    after = slo_lab.run(malformed=True)
    moved = {s for s in NORMAL_GOOD if not same(normal, after, s)}
    assert moved == {"decision_validity", "resolution"}
    assert (
        after.good["decision_validity"],
        after.valid["decision_validity"],
    ) == (0, 30)
    burn = after.burn("decision_validity")
    assert burn == 1000
    assert errorbudget.lasts_hours(burn) * 60 == Decimal("40.32")
    assert after.good["resolution"] == 86
    assert (
        "could not confirm your refund"
        in after.texts["refund_request"]
    )


def test_fs17(normal: slo_lab.Hour) -> None:
    after = slo_lab.run(guardrail="2")
    assert (
        after.good["not_refused"],
        after.valid["not_refused"],
    ) == (90, 120)
    burn = after.burn("not_refused")
    assert burn == 50
    assert errorbudget.lasts_hours(burn) == Decimal("13.44")
    assert after.valid["decision_validity"] == 0
    assert after.burn("decision_validity") is None
    assert (
        after.good["policy_freshness"],
        after.valid["policy_freshness"],
    ) == (90, 90)
    for slo in (
        "availability",
        "ttfc_interactive",
        "ttfc_critical_action",
        "answer_cost",
    ):
        assert same(normal, after, slo)
    assert after.texts["refund_request"] == REFUSAL
    assert after.cost["refund_request"] == 0
    assert after.good["resolution"] == 86
    assert round(after.per_resolved, 7) == Decimal("0.0000959")
    fall = 1 - after.per_resolved / normal.per_resolved
    assert round(fall * 100) == 40  # cheaper by every cost measure
    assert (
        after.bad("not_refused") / after.valid["not_refused"] == 0.25
    )


def test_the_labs_print_their_findings(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fs05_lab.main()
    fs17_lab.main()
    out = capsys.readouterr().out
    assert "validity budget lasts 40 minutes" in out
    assert "refusal budget lasts 13.4 hours" in out
    assert "0.0001601 -> 0.0000959" in out
