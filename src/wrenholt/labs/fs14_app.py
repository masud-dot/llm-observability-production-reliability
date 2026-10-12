"""FS-14 lab app (SIMULATED misconfiguration, Chapter 7).

The real API with one mistake added: a debug line that logs every
customer question. FS14_PROTECT=1 adds the chapter's redaction, as
the production entry point does. Never deployed.
"""

import logging
import os

import wrenholt.api.app as api
from wrenholt.gateway import Gateway
from wrenholt.orchestrator.linnet import Answer, Linnet
from wrenholt.privacy.redact import protect
from wrenholt.telemetry.logs import to_stdout
from wrenholt.telemetry.setup import instrument
from wrenholt.tools.orders import OrdersClient

LOG = logging.getLogger("wrenholt.debug")


class Chatty(Linnet):
    async def answer(
        self,
        gateway: Gateway,
        model: str,
        question: str,
        orders: OrdersClient | None = None,
    ) -> Answer:
        LOG.info("debug question=%s", question)  # the mistake
        return await super().answer(gateway, model, question, orders)


vars(api)["Linnet"] = Chatty  # Linnet is an agent (Chapter 9)
to_stdout()
app = instrument(api.create_app())
if os.environ.get("FS14_PROTECT") == "1":
    protect()
