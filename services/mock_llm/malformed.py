"""FS-05 malformed refund decisions for the mock provider (SIMULATED).

After a model update, a refund decision carries the amount as the
customer wrote it, "£5.00", where the tool's schema asks for whole
pence. Every other choice is unchanged. Wraps Chapter 1's app
instead of changing it, as FS-06 and FS-11 do.
"""

import json
from typing import Any, cast

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.base import RequestResponseEndpoint


def malformed(call: dict[str, Any]) -> dict[str, Any]:
    function = call["function"]
    if function["name"] != "issue_refund":
        return call
    args = json.loads(function["arguments"])
    pounds, pence = divmod(args["amount_minor"], 100)
    args["amount_minor"] = f"£{pounds}.{pence:02d}"
    changed = {**function, "arguments": json.dumps(args)}
    return {**call, "function": changed}


def with_malformed_refunds(app: FastAPI) -> FastAPI:
    @app.middleware("http")
    async def rewrite(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        kind = response.headers.get("content-type", "")
        if (
            request.url.path != "/v1/chat/completions"
            or response.status_code != 200
            or not kind.startswith("application/json")
        ):
            return response
        stream = cast(StreamingResponse, response).body_iterator
        chunks = [
            c.encode() if isinstance(c, str) else bytes(c)
            async for c in stream
        ]
        data = json.loads(b"".join(chunks))
        for choice in data["choices"]:
            calls = choice["message"].get("tool_calls")
            if calls:
                choice["message"]["tool_calls"] = [
                    malformed(call) for call in calls
                ]
        return JSONResponse(data, status_code=200)

    return app
