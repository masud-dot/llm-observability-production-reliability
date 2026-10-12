"""Wrenholt support API.

The app emits no telemetry of its own, and turns FastAPI's built-in
telemetry off. Chapter 3 adds telemetry at the entry point, and only
when an OTLP endpoint is configured. Since Chapter 4 every model
call goes through the gateway; since Chapter 6 an order in the
question is looked up, and every answer leaves a reproduction
bundle. Since Chapter 8 an answer can be streamed.
"""

import json
import logging
from collections.abc import AsyncGenerator, AsyncIterator, Mapping
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from opentelemetry import trace
from opentelemetry.trace import Span
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from wrenholt import repro
from wrenholt.gateway import (
    Gateway,
    ProviderError,
    RetryPolicy,
    Route,
    StreamResult,
)
from wrenholt.orchestrator.linnet import answer, stream_answer
from wrenholt.orchestrator.prompts import SUPPORT
from wrenholt.privacy.vault import Vault
from wrenholt.telemetry import conventions as c
from wrenholt.telemetry.framework import FRAMEWORK_TELEMETRY_OFF
from wrenholt.tools.orders import OrdersClient

LOG = logging.getLogger("wrenholt.api")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WRENHOLT_")

    provider_url: str = "http://127.0.0.1:8100/v1"
    provider_b_url: str = "http://127.0.0.1:8102/v1"
    provider_key: str = "sk-mock"
    model: str = "mock-a-fast"
    # The Compose service name; local runs set WRENHOLT_ORDERS_URL.
    orders_url: str = "http://orders:8200"
    # Chapter 7: "off", or "vault" to keep content by reference.
    content_capture: str = "off"
    vault_path: str = ":memory:"
    vault_ttl_s: float = 72 * 3600


def routes(cfg: Settings) -> dict[str, Route]:
    """The routing table. Provider names are configuration: a real
    deployment routes to "openai" or "anthropic" here."""
    a = Route("wrenholt.mock_a", cfg.provider_url, cfg.provider_key)
    b = Route("wrenholt.mock_b", cfg.provider_b_url, cfg.provider_key)
    return {"mock-a-fast": a, "mock-a-large": a, "mock-b-standard": b}


# The response model each request model was validated against
# (Chapter 6). A different one is a silent model change: FS-11.
PINNED = {
    "mock-a-fast": "mock-a-fast-2026-09",
    "mock-a-large": "mock-a-large-2026-09",
    "mock-b-standard": "mock-b-standard-2026-09",
}


class ChatIn(BaseModel):
    message: str
    # Chapter 8: "stream": true answers with server-sent events.
    stream: bool = False


class ChatOut(BaseModel):
    answer: str


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings if settings is not None else Settings()
    table = routes(cfg)
    policy = RetryPolicy()
    gateway = Gateway(table, policy, pinned=PINNED)
    orders = OrdersClient(cfg.orders_url)
    vault = None
    if cfg.content_capture == "vault":
        vault = Vault(cfg.vault_path, cfg.vault_ttl_s)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await gateway.aclose()
        await orders.aclose()

    app = FastAPI(
        title="Wrenholt support API",
        lifespan=lifespan,
        telemetry=FRAMEWORK_TELEMETRY_OFF,
    )
    app.state.vault = vault

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    def keep(
        span: Span, question: str, text: str, seen: str, outcome: str
    ) -> None:
        """What every answer leaves behind: a reproduction bundle
        (Chapter 6) and, when capture is on, its content in the
        vault by reference (Chapter 7)."""
        request = span.get_span_context()
        item = repro.bundle(
            request,
            SUPPORT,
            seen,
            table[cfg.model],
            cfg.model,
            PINNED.get(cfg.model, ""),
            policy,
        )
        repro.record_later(item, request)
        if vault is not None:
            trace_id = format(request.trace_id, "032x")
            kept = {"question": question, "answer": text}
            kept["outcome"] = outcome
            ref = vault.put(trace_id, "wrenholt", kept)
            span.set_attribute(c.CONTENT_REF, ref)

    async def relay(
        span: Span,
        question: str,
        first: str,
        chunks: AsyncGenerator[str],
        done: StreamResult,
    ) -> AsyncIterator[str]:
        """Server-sent events for one streamed answer (Chapter 8).
        HTTP 200 went out with the first chunk, so a later failure
        can only be reported in-band, after the text already sent,
        which stays sent."""
        sent, outcome = [first], "complete"
        try:
            yield sse("chunk", {"text": first})
            async for piece in chunks:
                sent.append(piece)
                yield sse("chunk", {"text": piece})
            yield sse("done", {"finish": "stop"})
            LOG.info("chat answered")  # never the customer's words
        except ProviderError as err:
            outcome = "interrupted"
            LOG.warning("chat interrupted: %s", err.error_type.value)
            data = {"error": err.error_type.value, "partial": True}
            yield sse("error", data)
        finally:
            if done.cancelled:  # the customer left mid-answer
                outcome = "cancelled"
            keep(
                span,
                question,
                "".join(sent),
                done.response_model,
                outcome,
            )
            await chunks.aclose()

    @app.post("/chat", response_model=None)
    async def chat(body: ChatIn) -> ChatOut | StreamingResponse:
        span = trace.get_current_span()
        if body.stream:
            done = StreamResult()
            chunks = stream_answer(
                gateway, cfg.model, body.message, orders, done
            )
            try:  # the status code waits for the first chunk
                first = await anext(chunks)
            except ProviderError as err:
                LOG.warning("chat failed: %s", err.error_type.value)
                raise HTTPException(
                    503, "Linnet cannot answer now."
                ) from err
            events = relay(span, body.message, first, chunks, done)
            return StreamingResponse(
                events, media_type="text/event-stream"
            )
        try:
            result = await answer(
                gateway, cfg.model, body.message, orders
            )
        except ProviderError as err:
            # The trace holds the details; the customer gets none.
            LOG.warning("chat failed: %s", err.error_type.value)
            raise HTTPException(
                503, "Linnet cannot answer now."
            ) from err
        LOG.info("chat answered")  # never the customer's words
        model_seen = result.completion.response_model
        keep(span, body.message, result.text, model_seen, "complete")
        return ChatOut(answer=result.text)

    return app


def sse(kind: str, data: Mapping[str, object]) -> str:
    """One server-sent event (Chapter 8)."""
    return f"event: {kind}\ndata: {json.dumps(data)}\n\n"
