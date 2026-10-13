"""The SLO file (Chapter 12): a decision for every candidate, and
the checks a reviewer would otherwise make by eye."""

from decimal import Decimal
from typing import Any

import pytest
import yaml

from wrenholt.slo.catalog import load_catalog
from wrenholt.slo.objectives import (
    OBJECTIVES_PATH,
    Objectives,
    load_objectives,
)
from wrenholt.telemetry import conventions as c

SLOS = load_objectives()
# The Workbook's SLI types (Chapter 2), for the SLIs with objectives.
TYPES = {
    "availability": "availability",
    "ttfc": "latency",
    "decision_validity": "quality",
    "not_refused": "quality",
    "policy_freshness": "freshness",
    "answer_cost": "cost",
}


def raw() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(OBJECTIVES_PATH.read_text())
    return data


def test_every_candidate_has_a_decision() -> None:
    candidates = {s.id for s in load_catalog().slis}
    decided = {s.sli_id for s in SLOS.objectives}
    assert candidates <= decided
    added = {"not_refused", "answer_cost", "provider_attempts"}
    assert decided - candidates == added


def test_table_12_1() -> None:
    table = {
        s.slo: (s.layer, s.objective, s.owner)
        for s in SLOS.objectives
    }
    assert table == {
        "availability": ("L1", Decimal("0.999"), "platform"),
        "ttfc_interactive": ("L1", Decimal("0.99"), "platform"),
        "ttfc_critical_action": ("L1", Decimal("0.99"), "platform"),
        "decision_validity": ("L2", Decimal("0.999"), "assistant"),
        "not_refused": ("L2", Decimal("0.995"), "assistant"),
        "groundedness": ("L2", None, None),
        "policy_freshness": ("L3", Decimal("0.99"), "help-centre"),
        "answer_cost": ("L4", Decimal("0.99"), "platform"),
        "resolution": ("L4", None, None),
        "provider_attempts": ("L1", None, None),
    }
    assert SLOS.window == "28d"


def test_objectives_cover_five_sli_types_and_every_layer() -> None:
    held = [s for s in SLOS.objectives if s.objective is not None]
    assert {TYPES[s.sli_id] for s in held} == {
        "availability", "latency", "quality", "freshness", "cost"
    }  # fmt: skip
    assert {s.layer for s in held} == {"L1", "L2", "L3", "L4"}


def test_thresholds_are_the_candidates_and_bucket_boundaries() -> (
    None
):
    candidates = load_catalog().get("ttfc").thresholds_s
    timed = [
        s for s in SLOS.objectives if s.counted_by == "first_chunk"
    ]
    assert len(timed) == 2
    for s in timed:
        assert s.request_class is not None
        assert s.threshold_s == candidates[s.request_class]
        assert s.threshold_s in c.ANSWER_BUCKETS


def test_the_cost_threshold_sits_above_every_normal_answer() -> None:
    # Chapter 11, Table 11.2: the dearest answer is a refund's.
    assert SLOS.get("answer_cost").max_cost_usd == Decimal("0.0004")
    assert Decimal("0.0003336") < Decimal("0.0004")


@pytest.mark.parametrize(
    ("index", "change", "message"),
    [
        (1, {"threshold_s": 3.0}, "bucket boundary"),
        (0, {"owner": None}, "needs an owner"),
        (5, {"reason": None}, "an objective or a reason"),
        (0, {"counted_by": "events", "slo": "uptime"}, "no such SLI"),
        (7, {"max_cost_usd": None}, "cost threshold"),
    ],
)
def test_a_file_that_breaks_a_rule_does_not_load(
    index: int, change: dict[str, Any], message: str
) -> None:
    data = raw()
    entry = data["objectives"][index]
    for key, value in change.items():
        if value is None:
            entry.pop(key)
        else:
            entry[key] = value
    with pytest.raises(ValueError, match=message):
        Objectives.model_validate(data)
