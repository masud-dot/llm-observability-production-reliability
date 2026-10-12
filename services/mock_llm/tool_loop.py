"""FS-06 tool-call loop for the mock provider (SIMULATED).

Offered tools, the model asks for the same order lookup again and
again, whatever the last lookup returned: step repetition, which
MAST lists among the failure modes of multi-agent systems. Only
requests that offer tools and name an order change. Wraps
Chapter 1's app instead of changing it, as FS-11 does.
"""

import json
from typing import cast

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.base import RequestResponseEndpoint

from services.mock_llm.decide import ORDER, call


def with_tool_loop(app: FastAPI) -> FastAPI:
    @app.middleware("http")
    async def loop(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        sent = await request.body()  # read before the app runs
        response = await call_next(request)
        if request.url.path != "/v1/chat/completions":
            return response
        asked = json.loads(sent or b"{}")
        users = [
            m.get("content") or ""
            for m in asked.get("messages", [])
            if m.get("role") == "user"
        ]
        order = ORDER.search(users[0]) if users else None
        if response.status_code != 200 or not asked.get("tools"):
            return response
        if order is None:  # nothing to look up: pass through
            return response
        stream = cast(StreamingResponse, response).body_iterator
        chunks = [
            c.encode() if isinstance(c, str) else bytes(c)
            async for c in stream
        ]
        data = json.loads(b"".join(chunks))
        arrival = int(data["id"].rsplit("-", 1)[1])
        lookup = {"order_id": order.group()}
        data["choices"][0]["message"]["tool_calls"] = [
            call(arrival, 0, "lookup_order", lookup)
        ]
        data["choices"][0]["finish_reason"] = "tool_calls"
        return JSONResponse(data, status_code=200)

    return app
