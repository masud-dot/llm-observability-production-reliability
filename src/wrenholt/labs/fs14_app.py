"""FS-14 lab app (SIMULATED misconfiguration, Chapter 7).

The real API with one mistake added: a debug line that logs every
customer question. FS14_PROTECT=1 adds the chapter's redaction, as
the production entry point does. Never deployed.
"""

import logging
import os
from typing import Any

import wrenholt.api.app as api
from wrenholt.privacy.redact import protect
from wrenholt.telemetry.logs import to_stdout
from wrenholt.telemetry.setup import instrument

LOG = logging.getLogger("wrenholt.debug")
_answer = vars(api)["answer"]


async def chatty(*args: Any, **kwargs: Any) -> Any:
    LOG.info("debug question=%s", args[2])  # the misconfiguration
    return await _answer(*args, **kwargs)


vars(api)["answer"] = chatty
to_stdout()
app = instrument(api.create_app())
if os.environ.get("FS14_PROTECT") == "1":
    protect()
