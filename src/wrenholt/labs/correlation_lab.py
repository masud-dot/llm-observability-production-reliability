"""Correlation lab (Chapter 6): one chat, followed everywhere.

    uv run python scripts/correlation_lab.py

The orders service and Linnet run as child processes exporting to
a stand-in OTLP receiver; the mock provider records the headers it
receives. The chat asks about an order and arrives with baggage
from an upstream caller (SIMULATED workload).
"""

import json
import time
from dataclasses import dataclass

import httpx2
from opentelemetry import context, propagate
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.instrumentation.httpx import (
    HTTPX2ClientInstrumentor,
)
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.propagators.textmap import TextMapPropagator
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)

from services.mock_llm.server import running_provider
from services.otlp_standin import LogRecord, SpanRecord, StandIn
from services.outage_lab import Linnet, free_port
from wrenholt.telemetry import conventions as c

# What OTEL_PROPAGATORS gives when unset: trace context and baggage.
DEFAULT_PROPAGATORS = CompositePropagator(
    [TraceContextTextMapPropagator(), W3CBaggagePropagator()]
)
QUESTION = "Where is order WG-100006?"
UPSTREAM_BAGGAGE = "customer.email=jo%40example.com"


@dataclass(frozen=True)
class Run:
    spans: list[SpanRecord]
    logs: list[LogRecord]
    provider_headers: list[dict[str, str]]
    stdout: list[dict[str, object]]
    status: int


def run() -> Run:
    standin = StandIn(free_port())
    standin.up()
    headers: list[dict[str, str]] = []
    with running_provider(headers=headers) as mock:
        orders = Linnet(
            mock.base_url, standin.port, "2",
            "services.orders.main:app", name="orders",
        )  # fmt: skip
        url = f"http://127.0.0.1:{orders.port}"
        api = Linnet(
            mock.base_url, standin.port, "2",
            extra_env={"WRENHOLT_ORDERS_URL": url},
        )  # fmt: skip
        status, _ = api.ask(QUESTION, {"baggage": UPSTREAM_BAGGAGE})
        time.sleep(2.5)  # one batch delay, plus the bundle task
        api.stop()
        orders.stop()
    lines = [
        json.loads(line)
        for line in api.log.read_text().splitlines()
        if line.startswith("{")
    ]
    standin.down()
    return Run(
        standin.records(), standin.logs(), headers, lines, status
    )


def forwards_baggage(textmap: TextMapPropagator) -> bool:
    """Does upstream baggage reach the provider under this setting?
    Real HTTP client instrumentation; global state restored."""
    previous = propagate.get_global_textmap()
    propagate.set_global_textmap(textmap)
    instrumentor = HTTPX2ClientInstrumentor()
    instrumentor.instrument(tracer_provider=TracerProvider())
    headers: list[dict[str, str]] = []
    try:
        with running_provider(headers=headers) as mock:
            inbound = propagate.extract({"baggage": UPSTREAM_BAGGAGE})
            token = context.attach(inbound)
            try:
                ask = [{"role": "user", "content": "Refund?"}]
                body = {"model": "mock-a-fast", "messages": ask}
                url = f"{mock.base_url}/chat/completions"
                httpx2.post(url, json=body, timeout=5)
            finally:
                context.detach(token)
    finally:
        instrumentor.uninstrument()
        propagate.set_global_textmap(previous)
    return "baggage" in headers[0]


def request_trace(r: Run) -> str:
    (server,) = [
        s for s in r.spans if s.service == "linnet-api"
        and s.name == "POST /chat"
    ]  # fmt: skip
    return server.trace_id


def main() -> None:
    r = run()
    trace_id = request_trace(r)
    in_trace = [s for s in r.spans if s.trace_id == trace_id]
    services = sorted({s.service for s in in_trace})
    by_id = {s.span_id: s for s in in_trace}
    (order_span,) = [
        s for s in in_trace if s.service == "orders" and s.parent_id
    ]
    parent = by_id[order_span.parent_id]
    sent = r.provider_headers[0]
    print("Correlation lab (mock provider: SIMULATED)")
    print(f"chat: {QUESTION!r}, with baggage from upstream")
    print(f"trace {trace_id[:8]}: {len(in_trace)} spans in "
          f"{', '.join(services)}")  # fmt: skip
    print(f"  orders '{order_span.name}' has parent "
          f"{parent.service} '{parent.name}'")  # fmt: skip
    has_trace = trace_id in sent.get("traceparent", "")
    print(f"provider got traceparent with this trace: {has_trace}")
    print(f"provider got baggage: {'baggage' in sent}")
    otlp = [x for x in r.logs if x.trace_id == trace_id]
    lines = [x for x in r.stdout if x.get("trace_id") == trace_id]
    print(f"logs carrying the trace ID: {len(otlp)} over OTLP, "
          f"{len(lines)} on stdout")  # fmt: skip
    (record,) = [x for x in r.logs if c.REPRO_BUNDLE in x.attributes]
    bundle = json.loads(str(record.attributes[c.REPRO_BUNDLE]))
    (writer,) = [s for s in r.spans if s.trace_id == record.trace_id]
    linked = any(link.startswith(trace_id) for link in writer.links)
    print(f"bundle: own trace {record.trace_id[:8]}, linked to the "
          f"request: {linked}")  # fmt: skip
    version = bundle["service_version"]
    print(f"  names trace {bundle['trace_id'][:8]}; {len(bundle)} "
          f"fields; service.version {version}")  # fmt: skip
    print("risk check, the same upstream baggage:")
    default = forwards_baggage(DEFAULT_PROPAGATORS)
    linnet = forwards_baggage(TraceContextTextMapPropagator())
    print(f"  SDK default propagators: reaches provider: {default}")
    print(f"  Linnet, trace context only: reaches provider: {linnet}")
