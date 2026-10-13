"""The cardinality budget and its guard (Chapter 10), and the
token and cost metrics Chapter 11 adds to it."""

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
# Table 10.2: the metrics Chapter 10 budgeted.
TABLE_10_2 = {
    c.OPERATION_DURATION, c.TIME_TO_FIRST_CHUNK,
    c.TIME_PER_OUTPUT_CHUNK, c.ATTEMPTS, c.MODEL_MISMATCHES,
    c.REDACTIONS, c.AGENT_DURATION, c.AGENT_INFERENCE_CALLS,
    c.AGENT_TOOL_CALLS, c.TOOL_DURATION, c.RETURNED,
}  # fmt: skip


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
    # Chapter 11: one tenant has a limit; the prompt in force and
    # its successor while it rolls out; text is the only modality.
    tenants = len({Settings().tenant})
    versions = 2
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
        c.USAGE_INPUT: route * models,
        c.USAGE_OUTPUT: route * models,
        c.USAGE_CACHE_READ: route * models,
        c.OUTPUT_PER_CALL: route,
        c.COST: tenants * route * models * versions,
        c.LIMITED: tenants + 1,  # and OTHER
        c.SPEND_LIMIT: tenants,
        c.SLO_EVENTS: len(c.EVENT_SLIS) * 2,  # good or bad
        c.ANSWER_FIRST_CHUNK: len(c.REQUEST_CLASSES),
        # refusals by prompt version and policy accuracy by index
        # build, two of each during a rollout; groundedness, intent
        c.EVALUATION_RESULTS: 2 * versions + 2 * 2 + 2 + 4,
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
    table = {m: n for m, n in series.items() if m in TABLE_10_2}
    assert sum(table.values()) == 1871 <= c.SERIES_BUDGET
    points = sum(BUDGETS[m].combinations for m in TABLE_10_2)
    assert points == 151


def test_chapter_11_fits_the_budget() -> None:
    # Section 11.4: what the token and cost metrics add.
    series = {
        b.metric: b.series
        for b in c.BUDGET
        if b.metric not in CHAPTER_12 + CHAPTER_13
    }
    per = len(c.TOKEN_BUCKETS) + 3
    assert series[c.OUTPUT_PER_CALL] == 3 * per == 51
    assert 6 * per == 102  # had it kept the response model
    added = {m: n for m, n in series.items() if m not in TABLE_10_2}
    assert sum(added.values()) == 6 + 6 + 6 + 51 + 12 + 2 + 1 == 84
    assert sum(series.values()) == 1871 + 84 == 1955
    assert sum(series.values()) <= c.SERIES_BUDGET
    points = sum(
        b.combinations
        for b in c.BUDGET
        if b.metric not in CHAPTER_12 + CHAPTER_13
    )
    assert points == 151 + 36 == 187


CHAPTER_12 = (c.SLO_EVENTS, c.ANSWER_FIRST_CHUNK)
CHAPTER_13 = (c.EVALUATION_RESULTS,)


def test_chapter_12_fits_the_budget() -> None:
    # Section 12.5: the SLI events and the customer's first chunk.
    series = {
        b.metric: b.series
        for b in c.BUDGET
        if b.metric not in CHAPTER_13
    }
    assert series[c.SLO_EVENTS] == len(c.EVENT_SLIS) * 2 == 10
    per = len(c.ANSWER_BUCKETS) + 3
    assert series[c.ANSWER_FIRST_CHUNK] == 2 * per == 18
    assert 2 * (len(c.TTFC_BUCKETS) + 3) == 38  # the gateway's set
    assert sum(series.values()) == 1955 + 28 == 1983
    assert sum(series.values()) <= c.SERIES_BUDGET
    points = sum(
        b.combinations for b in c.BUDGET if b.metric not in CHAPTER_13
    )
    assert points == 187 + 12 == 199


def test_chapter_13_fits_the_budget() -> None:
    # Section 13.4: evaluation results take the last of the budget.
    series = {b.metric: b.series for b in c.BUDGET}
    assert series[c.EVALUATION_RESULTS] == 14
    assert sum(series.values()) == 1983 + 14 == 1997
    assert sum(series.values()) <= c.SERIES_BUDGET
    assert sum(b.combinations for b in c.BUDGET) == 199 + 14 == 213


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
