"""ASGI entry point:

uv run uvicorn wrenholt.api.main:app --app-dir src --port 8000

Telemetry starts only when OTEL_EXPORTER_OTLP_ENDPOINT is set
(Chapter 3); without it the API behaves exactly as in Chapter 1.
"""

from wrenholt.api.app import create_app
from wrenholt.privacy.redact import protect
from wrenholt.telemetry.logs import to_stdout
from wrenholt.telemetry.setup import instrument

to_stdout()  # JSON lines with trace IDs (Chapter 6)
app = instrument(create_app())
protect()  # redaction before export (Chapter 7)
