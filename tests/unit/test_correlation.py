"""Correlation: one chat, joined across services, logs and bundle.

Runs the orders service and Linnet as child processes exporting to
a stand-in OTLP receiver (about five seconds).
"""

import json

import pytest
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)

from wrenholt import __version__
from wrenholt.labs.correlation_lab import (
    DEFAULT_PROPAGATORS,
    Run,
    forwards_baggage,
    request_trace,
    run,
)
from wrenholt.telemetry import conventions as c


@pytest.fixture(scope="module")
def chat() -> Run:
    return run()


def test_one_trace_crosses_into_the_orders_service(chat: Run) -> None:
    trace_id = request_trace(chat)
    spans = [s for s in chat.spans if s.trace_id == trace_id]
    assert {s.service for s in spans} == {"linnet-api", "orders"}
    by_id = {s.span_id: s for s in spans}
    (served,) = [s for s in spans if s.service == "orders"]
    caller = by_id[served.parent_id]
    assert (caller.service, caller.name) == ("linnet-api", "GET")


def test_spans_carry_the_resource_attributes(chat: Run) -> None:
    (server,) = [s for s in chat.spans if s.name == "POST /chat"]
    assert server.resource[c.SERVICE_NAMESPACE] == "wrenholt"
    assert server.resource[c.SERVICE_VERSION] == __version__
    assert server.resource[c.DEPLOYMENT_ENVIRONMENT] == "local"


def test_the_provider_gets_trace_context_but_no_baggage(
    chat: Run,
) -> None:
    # Since Chapter 9: two tool-loop decisions, then the answer.
    assert len(chat.provider_headers) == 3
    for sent in chat.provider_headers:
        assert request_trace(chat) in sent["traceparent"]
        assert "baggage" not in sent


def test_logs_carry_the_trace_id_both_ways(chat: Run) -> None:
    trace_id = request_trace(chat)
    otlp = [x.body for x in chat.logs if x.trace_id == trace_id]
    lines = [
        x["message"]
        for x in chat.stdout
        if x.get("trace_id") == trace_id
    ]
    assert "chat answered" in otlp
    assert "chat answered" in lines


def test_the_bundle_is_linked_and_names_the_request(
    chat: Run,
) -> None:
    trace_id = request_trace(chat)
    (record,) = [
        x for x in chat.logs if c.REPRO_BUNDLE in x.attributes
    ]
    assert (
        record.trace_id != trace_id
    )  # recorded off the request path
    (writer,) = [
        s for s in chat.spans if s.trace_id == record.trace_id
    ]
    assert any(link.startswith(trace_id) for link in writer.links)
    bundle = json.loads(str(record.attributes[c.REPRO_BUNDLE]))
    assert bundle["trace_id"] == trace_id
    assert "WG-100006" not in json.dumps(bundle)


def test_default_propagators_would_leak_upstream_baggage() -> None:
    assert forwards_baggage(DEFAULT_PROPAGATORS) is True
    assert forwards_baggage(TraceContextTextMapPropagator()) is False
