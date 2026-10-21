"""Error-budget arithmetic (Chapter 12): every worked number."""

from decimal import Decimal

import pytest

from wrenholt.labs.fs12_lab import HOUR
from wrenholt.slo import errorbudget as eb
from wrenholt.slo.catalog import load_catalog
from wrenholt.slo.objectives import load_objectives

NINES = Decimal("0.999")


def test_a_budget_in_time_and_in_events() -> None:
    # Section 12.3: 99.9 per cent over 28 days.
    assert eb.WINDOW_HOURS == 28 * 24 == 672
    assert eb.budget(NINES) == Decimal("0.001")
    assert eb.budget(NINES) * eb.WINDOW_HOURS * 60 == Decimal("40.32")
    refunds = HOUR["refund_request"] * 672
    assert refunds == 20160
    assert eb.allowed_bad(NINES, refunds) == Decimal("20.16")
    answers = HOUR.total() * 672
    assert answers == 80640
    assert eb.allowed_bad(Decimal("0.995"), answers) == Decimal(
        "403.2"
    )
    assert eb.allowed_bad(Decimal("0.99"), answers) == Decimal(
        "806.4"
    )


def test_burn_rates_and_how_long_a_budget_lasts() -> None:
    assert eb.lasts_hours(Decimal(1)) == eb.WINDOW_HOURS
    fs05 = eb.burn_rate(30, 30, NINES)
    assert fs05 == 1000
    assert eb.lasts_hours(fs05) * 60 == Decimal("40.32")
    assert eb.spent(fs05, Decimal(1)) > 1  # overspent within the hour
    fs17 = eb.burn_rate(30, 120, Decimal("0.995"))
    assert fs17 == 50
    assert eb.lasts_hours(fs17) == Decimal("13.44")
    assert round(eb.spent(fs17, Decimal(1)) * 100, 2) == Decimal(
        "7.44"
    )


def test_remaining_budget() -> None:
    assert eb.remaining(0, 100, Decimal("0.99")) == 1
    assert eb.remaining(1, 100, Decimal("0.99")) == 0
    # the promtool test's FS-17 hour, read as a whole window
    assert eb.remaining(30, 120, Decimal("0.995")) == -49


def test_low_traffic() -> None:
    # 30 refund decisions an hour: 2.5 in a five-minute window, and
    # the catalogue's minimum of 30 events takes an hour to gather.
    assert Decimal(HOUR["refund_request"]) * 5 / 60 == Decimal("2.5")
    assert load_catalog().min_events == HOUR["refund_request"]
    assert round(eb.burn_rate(1, 3, NINES)) == 333


def test_impossible_inputs_are_refused() -> None:
    with pytest.raises(ValueError):
        eb.budget(Decimal(1))
    with pytest.raises(ValueError):
        eb.burn_rate(0, 0, NINES)


# Chapter 11's answers on mock-a-fast, and FS-12's thorough ones.
NORMAL = {
    "policy_question": Decimal("0.0000433"),
    "order_status": Decimal("0.0001883"),
    "refund_request": Decimal("0.0003336"),
}
FS12 = {
    "policy_question": Decimal("0.0001713"),
    "order_status": Decimal("0.0003163"),
    "refund_request": Decimal("0.0004616"),
}


def test_chapter_11_scenarios_against_the_cost_objective() -> None:
    cost = load_objectives().get("answer_cost")
    cap, objective = cost.max_cost_usd, cost.objective
    assert cap is not None and objective is not None

    def burn(per: dict[str, Decimal]) -> Decimal:
        bad = sum(n for j, n in HOUR.items() if per[j] > cap)
        return eb.burn_rate(bad, HOUR.total(), objective)

    fs13 = {j: v * 5 for j, v in NORMAL.items()}  # mock-a-large
    assert burn(NORMAL) == 0
    assert burn(FS12) == 25
    assert eb.lasts_hours(burn(FS12)) == Decimal("26.88")
    assert burn(fs13) == 50
    assert eb.lasts_hours(burn(fs13)) == Decimal("13.44")


# Valid events in FS-09's normal hour, as the labs count them.
PER_HOUR = {
    "availability": 120,
    "ttfc_interactive": 90,
    "ttfc_critical_action": 30,
    "decision_validity": 30,
    "not_refused": 120,
    "policy_freshness": 120,
    "answer_cost": 120,
}


def test_table_12_1_budgets() -> None:
    slos = load_objectives()
    allowed = {
        slo: eb.allowed_bad(objective, n * 672)
        for slo, n in PER_HOUR.items()
        if (objective := slos.get(slo).objective) is not None
    }
    assert allowed == {
        "availability": Decimal("80.64"),
        "ttfc_interactive": Decimal("604.8"),
        "ttfc_critical_action": Decimal("201.6"),
        "decision_validity": Decimal("20.16"),
        "not_refused": Decimal("403.2"),
        "policy_freshness": Decimal("806.4"),
        "answer_cost": Decimal("806.4"),
    }
    # freshness: hours of wholly stale answers a window allows
    assert eb.budget(Decimal("0.99")) * eb.WINDOW_HOURS == Decimal(
        "6.72"
    )


def test_the_policy_thresholds() -> None:
    # 20 per cent of a budget in one incident means a postmortem.
    fs05, fs17 = Decimal(1000), Decimal(50)
    assert eb.lasts_hours(fs05) * 60 * Decimal("0.2") == Decimal(
        "8.064"
    )
    assert eb.lasts_hours(fs17) * Decimal("0.2") == Decimal("2.688")
    assert round(eb.spent(fs05, Decimal(1)), 3) == Decimal("1.488")
