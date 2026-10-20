"""Turn FastAPI's built-in telemetry off (Chapter 3).

FastAPI 0.142 can add OTLP exporters from OTEL_* variables and emit
its own spans, metrics and exception logs, including rejected
request input. Wrenholt's telemetry has one owner, setup.py, so
every Wrenholt app passes this to FastAPI().
"""

from fastapi.telemetry import TelemetryConfig

FRAMEWORK_TELEMETRY_OFF: TelemetryConfig = {
    "auto_configure": False,
    "tracing": False,
    "metrics": False,
    "logs": False,
    "operation_spans": False,
}
