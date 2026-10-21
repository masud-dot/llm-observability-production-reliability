"""FS-18 spend-cap exhaustion for the mock provider (SIMULATED).

An exhausted spend cap answers every request with HTTP 429, an
OpenAI-style billing code and no retry-after: waiting cannot help
until someone raises the cap. The fault wraps Chapter 1's app
instead of changing it, and records each rejected request in the
same provider log, so attempts stay countable.
"""

import time

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

from services.mock_llm.app import (
    RETRY_COUNT_HEADER,
    ProviderLog,
    Received,
)

SPEND_CAP_BODY = {
    "error": {
        "type": "insufficient_quota",
        "code": "project_spend_limit_exceeded",
        "message": "Project spend limit reached.",
    }
}


def with_spend_cap(app: FastAPI, log: ProviderLog) -> FastAPI:
    @app.middleware("http")
    async def spend_cap(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path != "/v1/chat/completions":
            return await call_next(request)
        at_ns = time.time_ns()
        arrival = len(log)
        retry_count = request.headers.get(RETRY_COUNT_HEADER)
        log.add(Received(arrival, at_ns, 429, retry_count))
        return JSONResponse(SPEND_CAP_BODY, status_code=429)

    return app
