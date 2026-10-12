"""SLI calculators: worked numbers you can check by hand."""

from wrenholt.slo.catalog import load_catalog
from wrenholt.slo.events import Outcome, RequestEvent
from wrenholt.slo.fs09 import IN_FORCE, SUPERSEDED, night_hour
from wrenholt.slo.sli import Context, measure

CATALOG = load_catalog()
CONTEXT = Context(policy_in_force=IN_FORCE)


def test_availability_counts_only_valid_requests() -> None:
    outcomes: list[Outcome] = [
        "ok",
        "ok",
        "ok",
        "server_error",
        "client_error",
        "cancelled",
        "ok",
        "server_error",
    ]
    events = [
        RequestEvent("order_status", "interactive", o)
        for o in outcomes
    ]
    result = measure(CATALOG.get("availability"), events, CONTEXT)
    # 8 requests; 2 are not valid (client error, cancellation);
    # 4 of the remaining 6 succeeded.
    assert (result.good, result.valid) == (4, 6)
    assert result.ratio == 4 / 6


def test_latency_uses_the_request_class_threshold() -> None:
    events = [
        RequestEvent("policy_question", "interactive", "ok", 1.0),
        RequestEvent("policy_question", "interactive", "ok", 3.0),
        RequestEvent("refund_request", "critical_action", "ok", 3.0),
        RequestEvent("refund_request", "critical_action", "ok", 4.5),
        RequestEvent("order_status", "interactive", "server_error"),
    ]
    result = measure(CATALOG.get("ttfc"), events, CONTEXT)
    # 3.0 s fails the 2.5 s interactive threshold but passes the
    # 4.0 s critical-action one; the failed request is not timed.
    assert (result.good, result.valid) == (2, 4)


def test_freshness_counts_answers_that_used_a_policy() -> None:
    events = [
        RequestEvent(
            "policy_question", "interactive", "ok", 1.0, IN_FORCE
        ),
        RequestEvent(
            "policy_question", "interactive", "ok", 1.0, SUPERSEDED
        ),
        RequestEvent(
            "refund_request", "critical_action", "ok", 2.0, IN_FORCE
        ),
        RequestEvent("order_status", "interactive", "ok", 0.9),
    ]
    result = measure(CATALOG.get("policy_freshness"), events, CONTEXT)
    assert (result.good, result.valid) == (2, 3)


def test_low_traffic_keeps_counts_but_withholds_the_ratio() -> None:
    spec = CATALOG.get("availability")
    result = measure(spec, night_hour(), CONTEXT, CATALOG.min_events)
    # 12 requests, one failed: 11/12 would read as 91.7 %, but 12
    # is below the catalog's 30-event minimum.
    assert (result.good, result.valid) == (11, 12)
    assert result.ratio is None


def test_no_valid_events_gives_no_ratio() -> None:
    spec = CATALOG.get("decision_validity")
    events = [
        RequestEvent("policy_question", "interactive", "ok", 1.0)
    ]
    result = measure(spec, events, CONTEXT)
    assert (result.good, result.valid, result.ratio) == (0, 0, None)
