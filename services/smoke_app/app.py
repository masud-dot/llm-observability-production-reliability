"""Smoke app: one span, one metric point and one log
record per /smoke call, exported over OTLP/HTTP."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

RESOURCE = Resource.create()  # service.name from OTEL_SERVICE_NAME

TRACER_PROVIDER = TracerProvider(resource=RESOURCE)
TRACER_PROVIDER.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter())
)
trace.set_tracer_provider(TRACER_PROVIDER)

METER_PROVIDER = MeterProvider(
    resource=RESOURCE,
    metric_readers=[
        PeriodicExportingMetricReader(OTLPMetricExporter())
    ],
)
metrics.set_meter_provider(METER_PROVIDER)

LOGGER_PROVIDER = LoggerProvider(resource=RESOURCE)
LOGGER_PROVIDER.add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter())
)
set_logger_provider(LOGGER_PROVIDER)

LOG = logging.getLogger("smoke")
LOG.setLevel(logging.INFO)
LOG.addHandler(
    LoggingHandler(
        level=logging.INFO, logger_provider=LOGGER_PROVIDER
    )
)

TRACER = trace.get_tracer("smoke-app")
REQUESTS = metrics.get_meter("smoke-app").create_counter(
    "smoke.requests",
    unit="{request}",
    description="Smoke requests served.",
)

app = FastAPI(title="smoke-app")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/smoke")
def smoke() -> dict[str, str]:
    with TRACER.start_as_current_span("smoke.request") as span:
        trace_id = format(span.get_span_context().trace_id, "032x")
        REQUESTS.add(1, {"route": "/smoke"})
        LOG.info("smoke log trace_id=%s", trace_id)
    TRACER_PROVIDER.force_flush()
    LOGGER_PROVIDER.force_flush()
    METER_PROVIDER.force_flush()
    return {"trace_id": trace_id}
