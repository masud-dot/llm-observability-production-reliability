"""The catalog and the request map agree with each other."""

import pytest
import yaml
from pydantic import ValidationError

from wrenholt.slo.catalog import (
    CATALOG_PATH,
    Catalog,
    load_catalog,
)
from wrenholt.slo.request_map import load_request_map
from wrenholt.slo.sli import RULES

CATALOG = load_catalog()
MAP = load_request_map()


def test_every_layer_has_a_candidate_sli() -> None:
    layers = sorted({s.layer for s in CATALOG.slis})
    assert layers == ["L1", "L2", "L3", "L4"]
    assert len(CATALOG.slis) == 6


def test_every_kind_has_a_calculator() -> None:
    assert {s.kind for s in CATALOG.slis} <= set(RULES)


def test_every_sli_is_measured_somewhere_on_the_map() -> None:
    for spec in CATALOG.slis:
        assert spec.measured_at in MAP.ids(), spec.id


def test_budgets_fit_inside_the_deadline() -> None:
    # 0.1 + 0.6 + 0.8 + 2.5 + 0.2 + 1.0 + 4.0 + 0.0 = 9.2 s
    assert MAP.budget_through("outcome") == 9.2
    assert MAP.budget_through("outcome") <= MAP.deadline_s == 10.0


def test_first_chunk_budget_meets_the_ttfc_threshold() -> None:
    # 0.1 + 0.6 + 0.8 + 2.5 = 4.0 s, the critical-action threshold.
    first = MAP.budget_through(MAP.first_chunk_after)
    threshold = CATALOG.get("ttfc").thresholds_s[MAP.request_class]
    assert first == threshold == 4.0


def test_no_step_waits_on_a_non_critical_dependency() -> None:
    optional = {d.id for d in MAP.dependencies if not d.critical}
    assert optional == {"telemetry", "evaluation"}
    for step in MAP.steps:
        assert not set(step.depends_on) & optional, step.id


def test_a_duplicate_sli_id_is_rejected() -> None:
    data = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    data["slis"].append(dict(data["slis"][0]))
    with pytest.raises(ValidationError, match="unique"):
        Catalog.model_validate(data)
