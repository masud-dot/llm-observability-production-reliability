"""Linnet without the lifespan flush: the outage lab's control.

Identical to wrenholt.api.main except that flush_on_shutdown() is
left out, so the lab can show what uvicorn's SIGTERM handling does
to telemetry that has not been exported yet.
"""

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from wrenholt.api.app import create_app
from wrenholt.telemetry.setup import start_telemetry

app = create_app()
if start_telemetry() is not None:
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="healthz",
        exclude_spans=["receive", "send"],
    )
