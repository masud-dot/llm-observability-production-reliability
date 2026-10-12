"""SDK providers and OTLP/HTTP exporters, switched on by config.

Telemetry starts only when OTEL_EXPORTER_OTLP_ENDPOINT is set; the
standard OTEL_* variables supply everything else, so this module
names no endpoint, service or attribute. Export runs on background
threads with bounded queues: a slow or absent Collector costs
telemetry, not customer requests.
"""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from opentelemetry import metrics, propagate, trace
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
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import (
    HTTPX2ClientInstrumentor,
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
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)

from wrenholt import __version__
from wrenholt.telemetry import conventions as c


@dataclass(frozen=True)
class Providers:
    tracing: TracerProvider
    metering: MeterProvider
    logging: LoggerProvider

    def shutdown(self) -> None:
        """Flush and stop. Each export waits at most the exporter
        timeout, OTEL_EXPORTER_OTLP_TIMEOUT, read in seconds."""
        self.tracing.shutdown()
        self.metering.shutdown()
        self.logging.shutdown()


def start_telemetry() -> Providers | None:
    """Install providers and exporters; None if telemetry is off."""
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return None
    # Stable HTTP names (as in Chapter 1). Instrumentations read this
    # once, at their first instrument() call, so it is set first.
    os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "http")
    resource = Resource.create()  # reads OTEL_SERVICE_NAME
    tracing = TracerProvider(resource=resource)
    tracing.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracing)
    reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    metering = MeterProvider(
        resource=resource, metric_readers=[reader]
    )
    metrics.set_meter_provider(metering)
    logs = LoggerProvider(resource=resource)
    logs.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter())
    )
    set_logger_provider(logs)
    # Only Wrenholt's loggers export. The SDK's own warnings stay on
    # stderr, so a failing exporter never feeds its own queue.
    ours = logging.getLogger("wrenholt")
    ours.setLevel(logging.INFO)
    ours.addHandler(LoggingHandler(logger_provider=logs))
    return Providers(tracing, metering, logs)


def flush_on_shutdown(app: FastAPI, providers: Providers) -> None:
    """Flush telemetry when the app's lifespan ends.

    Uvicorn re-raises SIGTERM after a graceful shutdown, so atexit
    hooks, the SDK's own flush among them, never run. The lifespan
    is the last place where the process can still export. Wrenholt
    apps keep no lifespan state, so none is passed on.
    """
    inner = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(asgi_app: FastAPI) -> AsyncIterator[None]:
        async with inner(asgi_app):
            yield
        await asyncio.to_thread(providers.shutdown)

    app.router.lifespan_context = lifespan


def resource_defaults() -> None:
    """Add service.namespace, service.version and
    deployment.environment.name to OTEL_RESOURCE_ATTRIBUTES, unless
    the operator already set them (Chapter 6)."""
    wanted = {
        c.SERVICE_NAMESPACE: "wrenholt",
        c.SERVICE_VERSION: os.environ.get(
            "WRENHOLT_VERSION", __version__
        ),
        c.DEPLOYMENT_ENVIRONMENT: os.environ.get(
            "WRENHOLT_ENVIRONMENT", "local"
        ),
    }
    current = os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "")
    have = {
        p.split("=", 1)[0].strip() for p in current.split(",") if p
    }
    extra = [f"{k}={v}" for k, v in wanted.items() if k not in have]
    if extra:
        joined = ",".join([current, *extra] if current else extra)
        os.environ["OTEL_RESOURCE_ATTRIBUTES"] = joined


def instrument(app: FastAPI) -> FastAPI:
    """Add HTTP server spans and metrics, and outbound HTTP client
    spans, when telemetry is on."""
    resource_defaults()
    providers = start_telemetry()
    if providers is not None:
        # W3C trace context only (Chapter 6): baggage is neither
        # accepted from callers nor forwarded, so nothing an upstream
        # service put in it can reach a model provider.
        propagate.set_global_textmap(TraceContextTextMapPropagator())
        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls="healthz",
            exclude_spans=["receive", "send"],
        )
        # Outbound HTTP spans: one under each gateway attempt.
        HTTPX2ClientInstrumentor().instrument()
        flush_on_shutdown(app, providers)
    return app
