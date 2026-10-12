"""ASGI entry point for running the mock provider on its own.

    MOCK_LLM_PLAN=fs01 uv run uvicorn services.mock_llm.main:app \\
        --port 8100

MOCK_LLM_PROVIDER=b starts provider B, the fallback (Chapter 3).
MOCK_LLM_PLAN=fs18 exhausts the spend cap (Chapter 4).
MOCK_LLM_PLAN=fs11 silently changes the model version (Chapter 6).
Streamed requests are answered on a schedule (Chapter 8):
MOCK_LLM_PLAN=fs02 delays the first chunk, fs04 cuts the stream.
MOCK_LLM_PLAN=fs06 repeats the order lookup (Chapter 9).
"""

import os

from services.mock_llm.app import ProviderLog, create_app
from services.mock_llm.faults import NO_FAULTS, PLANS
from services.mock_llm.model_swap import FS11_SWAP, with_model_swap
from services.mock_llm.spend_cap import with_spend_cap
from services.mock_llm.streaming import SCHEDULES, STEADY, Streaming
from services.mock_llm.tool_loop import with_tool_loop

PLAN = os.environ.get("MOCK_LLM_PLAN", "none")
LOG = ProviderLog()
if PLAN == "fs18":
    api = with_spend_cap(create_app(NO_FAULTS, LOG), LOG)
elif PLAN == "fs11":
    api = with_model_swap(create_app(NO_FAULTS, LOG), FS11_SWAP)
elif PLAN == "fs06":
    api = with_tool_loop(create_app(NO_FAULTS, LOG))
elif PLAN in SCHEDULES:
    api = create_app(NO_FAULTS, LOG)
else:
    api = create_app(PLANS[PLAN], LOG)


@api.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


# Streamed requests are answered on the plan's schedule; everything
# else passes straight through to the app above.
app = Streaming(api, SCHEDULES.get(PLAN, STEADY))
