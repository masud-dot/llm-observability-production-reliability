"""ASGI entry point for the orders service:

PYTHONPATH=src uv run uvicorn services.orders.main:app --port 8200
"""

from services.orders.app import create_app
from services.orders.faults import Faults
from services.orders.store import OrderStore, generate_orders
from wrenholt.privacy.redact import protect
from wrenholt.telemetry.logs import to_stdout
from wrenholt.telemetry.setup import instrument

to_stdout()  # JSON lines with trace IDs (Chapter 6)
app = instrument(
    create_app(OrderStore(generate_orders()), Faults.from_env())
)
protect()  # redaction before export (Chapter 7)
