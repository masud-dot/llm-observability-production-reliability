"""FS-11 silent model change for the mock provider (SIMULATED).

The provider starts answering a model alias with a newer model
version, as real providers do when they update what an alias
points at. Requests and statuses are unchanged; only the response's
"model" field moves. Wraps Chapter 1's app instead of changing it.
"""

import json
from collections.abc import Mapping
from typing import cast

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.base import RequestResponseEndpoint

FS11_SWAP = {"mock-a-fast-2026-09": "mock-a-fast-2026-10"}


def with_model_swap(
    app: FastAPI, swaps: Mapping[str, str]
) -> FastAPI:
    @app.middleware("http")
    async def swap(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        if request.url.path != "/v1/chat/completions":
            return response
        if response.status_code != 200:
            return response
        stream = cast(StreamingResponse, response).body_iterator
        chunks = [
            c.encode() if isinstance(c, str) else bytes(c)
            async for c in stream
        ]
        data = json.loads(b"".join(chunks))
        data["model"] = swaps.get(data["model"], data["model"])
        return JSONResponse(data, status_code=200)

    return app
