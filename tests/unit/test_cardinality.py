"""The cardinality budget and its guard (Chapter 10)."""

import logging
import typing

import pytest
from opentelemetry.sdk.metrics.export import (
    HistogramDataPoint,
    InMemoryMetricReader,
)

from wrenholt.api.app import Settings, routes
from wrenholt.gateway.errors import ErrorType
from wrenholt.orchestrator.guard import (
    FINISHED,
    NO_TOOLS,
    REPEATED,
    STEP_LIMIT,
)
from wrenholt.privacy.classify import PATTERNS
from wrenholt.privacy.contract import FIELDS, DataClass
from wrenholt.rag.embed import EMBEDDERS
from wrenholt.telemetry import budget, setup
from wrenholt.telemetry import conventions as c
from wrenholt.tools.errors import ToolErrorType
from wrenholt.tools.toolbox import SCHEMAS

BUDGETS = {b.metric: b for b in c.BUDGET}


def test_every_metric_has_one_budget() -> None:
    metrics = {n.name for n in c.REGISTRY if n.kind == "metric"}
    assert set(BUDGETS) == metrics
    assert len(c.BUDGET) == len(BUDGETS)


def test_budgeted_attributes_are_operational() -> None:
    # Never an identifier (Chapter 7's data contract): those
    # belong on spans, where they cost nothing per value.
    for b in c.BUDGET:
        for key in b.attributes:
            data_class = FIELDS[key]
            assert data_class is DataClass.OPERATIONAL, b.metric


def test_combinations_follow_from_the_code() -> None:
    route = len(routes(Settings()))  # 3 request models
    models = 2  # the pinned model, and one substitute (FS-11)
    errors = len(ErrorType)  # 8
    stops = len({FINISHED, REPEATED, STEP_LIMIT, NO_TOOLS})
    names = len(c.TOOLS) + 1  # and OTHER
    places = 2  # span and log (Chapter 7)
    found = {b.metric: b.combinations for b in c.BUDGET}
    assert found == {
        # chat: a response model, an error, or a stream cut after
        # its model was known; retrieval; one per embedder
        c.OPERATION_DURATION: route * (models + errors + models)
        + 1
        + len(EMBEDDERS),
        c.TIME_TO_FIRST_CHUNK: route * models,
        c.TIME_PER_OUTPUT_CHUNK: route * models,
        c.ATTEMPTS: route * (1 + errors),
        c.MODEL_MISMATCHES: route * (models - 1),
        c.REDACTIONS: len(PATTERNS) * places,
        c.AGENT_DURATION: stops * (1 + errors),
        c.AGENT_INFERENCE_CALLS: 1,
        c.AGENT_TOOL_CALLS: 1,
        c.TOOL_DURATION: names * (1 + len(ToolErrorType)),
        c.RETURNED: 1 * 2,  # one data source, two index builds
    }


def test_the_worked_numbers() -> None:
    # Section 10.3.2: chat alone, 3 routes x 12 outcomes x 17 series.
    per = len(c.DURATION_BUCKETS) + 3
    assert 3 * (2 + len(ErrorType) + 2) * per == 612
    series = {b.metric: b.series for b in c.BUDGET}
    assert series[c.OPERATION_DURATION] == 39 * (14 + 3) == 663
    assert series[c.TIME_TO_FIRST_CHUNK] == 6 * (16 + 3) == 114
    assert series[c.AGENT_DURATION] == 36 * (13 + 3) == 576
    assert series[c.ATTEMPTS] == 27
    assert series[c.RETURNED] == 2 * (4 + 3) == 14
    assert sum(series.values()) == 1871 <= c.SERIES_BUDGET
    assert sum(b.combinations for b in c.BUDGET) == 151


def test_the_tools_offered_are_the_closed_set() -> None:
    assert c.TOOLS == tuple(SCHEMAS)
    assert c.CLOSED == {c.TOOL_NAME: c.TOOLS}


@pytest.fixture
def warned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(budget, "_warned", set())


@pytest.mark.usefixtures("warned")
def test_the_guard_drops_what_the_budget_leaves_out(
    caplog: pytest.LogCaptureFixture,
) -> None:
    attributes = {
        c.PROVIDER_NAME: "wrenholt.mock_a",
        c.ERROR_TYPE: "timeout",
        c.RESPONSE_ID: "resp-0001",  # an identifier
    }
    with caplog.at_level(logging.WARNING):
        kept = budget.guard(c.ATTEMPTS, attributes)
        budget.guard(c.ATTEMPTS, attributes)
    assert kept == {
        c.PROVIDER_NAME: "wrenholt.mock_a",
        c.ERROR_TYPE: "timeout",
    }
    # Once, by name only: the value may be what the budget keeps out.
    assert [r.getMessage() for r in caplog.records] == [
        f"{c.ATTEMPTS}: {c.RESPONSE_ID} is not in its budget"
    ]


def test_a_tool_name_outside_the_closed_set_becomes_other() -> None:
    attributes = {
        c.TOOL_NAME: "drop_all_orders",  # the model's own invention
        c.TOOL_TYPE: "function",
        c.AGENT_NAME: "Linnet",
    }
    kept = budget.guard(c.TOOL_DURATION, attributes)
    assert kept is not None
    assert kept[c.TOOL_NAME] == c.OTHER
    for name in c.TOOLS:
        attributes[c.TOOL_NAME] = name
        kept = budget.guard(c.TOOL_DURATION, attributes)
        assert kept is not None
        assert kept[c.TOOL_NAME] == name


def test_the_provider_guards_what_is_recorded() -> None:
    reader = InMemoryMetricReader()
    meters = budget.MeterProvider(metric_readers=[reader])
    meter = meters.get_meter("wrenholt.test")
    attempts = meter.create_counter(c.ATTEMPTS, unit="{attempt}")
    attempts.add(1, {c.PROVIDER_NAME: "p", c.RESPONSE_ID: "r-1"})
    tools = meter.create_histogram(
        c.TOOL_DURATION,
        unit="s",
        explicit_bucket_boundaries_advisory=c.DURATION_BUCKETS,
    )
    tools.record(0.2, {c.TOOL_NAME: "drop_all_orders"})
    other = meter.create_counter("test.unbudgeted")
    other.add(1, {"anything": "kept"})
    data = reader.get_metrics_data()
    assert data is not None
    points = {
        m.name: m.data.data_points[0]
        for r in data.resource_metrics
        for s in r.scope_metrics
        for m in s.metrics
    }
    assert points[c.ATTEMPTS].attributes == {c.PROVIDER_NAME: "p"}
    histogram = points[c.TOOL_DURATION]
    assert isinstance(histogram, HistogramDataPoint)
    assert histogram.attributes == {c.TOOL_NAME: c.OTHER}
    assert tuple(histogram.explicit_bounds) == c.DURATION_BUCKETS
    # No budget, no guard: the HTTP instrumentations' metrics.
    unguarded = points["test.unbudgeted"].attributes
    assert unguarded == {"anything": "kept"}


def test_wrenholt_meters_through_the_guard() -> None:
    hints = typing.get_type_hints(setup.Providers)
    assert hints["metering"] is budget.MeterProvider
