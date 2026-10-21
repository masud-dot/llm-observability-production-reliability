"""FS-10, FS-09 and FS-16 through evaluation (Chapter 13): every
number the labs print. SIMULATED: mock provider."""

from decimal import Decimal

import pytest

from wrenholt.guardrail import REFUSAL
from wrenholt.labs import fs09_index_lab, fs10_lab, fs16_lab
from wrenholt.labs.eval_lab import RATE, hours_to
from wrenholt.labs.fs12_lab import HOUR
from wrenholt.slo import errorbudget as eb


def test_fs10_prompt_regression() -> None:
    r = fs10_lab.run_lab()
    assert all(s.linked and s.events for s in r.before.values())
    before = {j: s.labels["refusal"] for j, s in r.before.items()}
    after = {j: s.labels["refusal"] for j, s in r.after.items()}
    assert set(before.values()) == {"answer"}
    assert after == {
        "policy_question": "answer",
        "order_status": "refusal",
        "refund_request": "answer",
    }
    assert (
        REFUSAL not in r.after["order_status"].text
    )  # not the guardrail
    assert (r.refusals(r.before), r.refusals(r.after)) == (0, 30)
    hours, shift = r.flagged(1.0)
    assert hours == 3 and shift is not None and shift.flagged
    assert round(shift.statistic, 1) == 22.5
    hours, shift = r.flagged(0.1)
    assert hours == 25 and shift is not None and shift.flagged
    assert round(shift.statistic, 1) == 21.7


def test_fs09_two_index_builds() -> None:
    r = fs09_index_lab.run_lab()
    assert "60 days" in r.stale.text and "30 days" in r.current.text
    assert r.stale.labels["groundedness"] == "grounded"
    assert r.stale.labels["policy_accuracy"] == "incorrect"
    assert r.current.labels["policy_accuracy"] == "correct"
    assert r.hours == 10


def test_fs16_intent_drift() -> None:
    r = fs16_lab.run_lab()
    assert r.seen["sale"].labels == {
        "intent": "other",
        "refusal": "answer",
    }
    hours, shift = r.flagged()
    assert hours == 2 and shift is not None
    assert shift.statistic == pytest.approx(0.375)


def test_the_labs_print_their_findings(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fs10_lab.main()
    fs09_index_lab.main()
    fs16_lab.main()
    out = capsys.readouterr().out
    assert "10% canary, 10% evaluated: flagged after 25 hours" in out
    assert "groundedness grounded, accuracy incorrect" in out
    assert "intent mix flagged after 2 hours (distance 0.375)" in out


def test_the_worked_numbers() -> None:
    # Section 13.1: a four-hour canary at 10 per cent of traffic,
    # a tenth of it evaluated.
    assert round(HOUR.total() * 0.1 * RATE * 4, 1) == 4.8
    assert hours_to(HOUR.total() * 0.1 * RATE) == 25
    # Section 13.4: groundedness counts evaluated policy answers.
    per_hour = HOUR["policy_question"] * RATE
    assert per_hour == 6 and hours_to(per_hour) == 5
    assert per_hour * 672 == 4032
    assert round(eb.allowed_bad(Decimal("0.99"), 4032), 2) == Decimal(
        "40.32"
    )
