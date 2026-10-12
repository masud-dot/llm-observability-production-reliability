"""Record the headers each chat request arrives with (Chapter 6),
to show exactly which context reaches a model provider."""

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint


def with_header_log(
    app: FastAPI, sink: list[dict[str, str]]
) -> FastAPI:
    @app.middleware("http")
    async def keep(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path == "/v1/chat/completions":
            sink.append(
                {k.lower(): v for k, v in request.headers.items()}
            )
        return await call_next(request)

    return app
