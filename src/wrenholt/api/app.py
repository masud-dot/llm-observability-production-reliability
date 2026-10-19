"""Wrenholt support API.

The app emits no telemetry of its own, and turns FastAPI's built-in
telemetry off. Chapter 3 adds telemetry at the entry point, and only
when an OTLP endpoint is configured. Since Chapter 4 every model
call goes through the gateway; since Chapter 6 an order in the
question is looked up, and every answer leaves a reproduction
bundle. Since Chapter 8 an answer can be streamed. Since Chapter 9
Linnet is an agent: it retrieves help-centre passages and calls
tools, and the handlers call it exactly as before. Since Chapter 11
every answer opens a bill that its model calls are charged to, and
a tenant over its spend limit gets HTTP 429. Since Chapter 12 a
guardrail screens each question first, the handlers judge the SLI
events only they can judge, and the help desk reports how each
conversation ended to /outcome.
"""

import json
import logging
import math
from collections.abc import AsyncGenerator, AsyncIterator, Mapping
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from opentelemetry import trace
from opentelemetry.trace import Span
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from wrenholt import repro
from wrenholt.evaluation.emitter import ResultEmitter
from wrenholt.evaluation.evaluators import standard
from wrenholt.evaluation.online import Evaluating
from wrenholt.gateway import (
    SPEND,
    Ledger,
    LimitExceeded,
    ProviderError,
    Route,
    Spend,
    StreamResult,
    load_prices,
)
from wrenholt.gateway.deadlines import deadline
from wrenholt.gateway.guarded import GuardedGateway
from wrenholt.gateway.retry import GuardedPolicy, RetryBudget
from wrenholt.guardrail import Guardrail
from wrenholt.orchestrator import linnet as running
from wrenholt.orchestrator.guard import LoopGuard
from wrenholt.orchestrator.linnet import Linnet
from wrenholt.orchestrator.prompts import SUPPORT, Prompt
from wrenholt.privacy.vault import Vault
from wrenholt.rag.corpus import snapshot
from wrenholt.rag.embed import EMBEDDERS
from wrenholt.rag.index import index_as_of
from wrenholt.slo.recorder import (
    CheckedRetriever,
    Screened,
    SliRecorder,
)
from wrenholt.telemetry import conventions as c
from wrenholt.telemetry.framework import FRAMEWORK_TELEMETRY_OFF
from wrenholt.tools.guarded import GuardedOrders

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
    # Chapter 9: the help-centre index, the embedder that built it,
    # the one that embeds questions, and the loop guard's limit.
    corpus_as_of: str = "2026-09-30"
    index_embedder: str = "wrenholt-embed-1"
    query_embedder: str = "wrenholt-embed-1"
    agent_max_steps: int = 5
    # Chapter 11: whose spend this is, its limit per clock hour in US
    # dollars, and the most tokens one model call may write.
    tenant: str = "wrenholt"
    spend_per_hour: str = "60.00"
    max_output_tokens: int = 512
    # Chapter 16: the answer's deadline end to end (Chapter 2), the
    # attempt timeout (set it from the provider's p99.9), retries a
    # minute for the process, and calls in flight per provider.
    deadline_s: float = 10.0
    attempt_timeout_s: float = 30.0
    retries_per_minute: int = 60
    in_flight: int = 64
    # Chapter 12: the guardrail's rule set (FS-17 runs version 2).
    guardrail_version: str = "1"
    # Chapter 13: the share of answers evaluated, chosen by trace ID.
    evaluation_rate: float = 0.1


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


class OutcomeIn(BaseModel):
    escalated: bool  # handed to a person, or not


def create_app(
    settings: Settings | None = None,
    slis: SliRecorder | None = None,
    results: ResultEmitter | None = None,
) -> FastAPI:
    cfg = settings if settings is not None else Settings()
    # Chapter 12: the SLI events the handlers judge.
    slis = slis if slis is not None else SliRecorder()
    table = routes(cfg)
    # Chapter 16: one retry budget for model and tool calls.
    budget = RetryBudget(cfg.retries_per_minute)
    policy = GuardedPolicy(budget)
    # Chapter 11: a routed model without a price stops start-up.
    prices = load_prices()
    if missing := prices.missing(table):
        raise ValueError(f"no price for {', '.join(missing)}")
    gateway = GuardedGateway(
        table,
        policy,
        pinned=PINNED,
        prices=prices,
        ledger=Ledger({cfg.tenant: Decimal(cfg.spend_per_hour)}),
        max_tokens=dict.fromkeys(table, cfg.max_output_tokens),
        attempt_timeout_s=cfg.attempt_timeout_s,
        in_flight=cfg.in_flight,
    )
    orders = GuardedOrders(cfg.orders_url, budget)
    # Chapter 9: an index built by another embedder stops start-up
    # here (FS-08), instead of answering every question emptily.
    index = index_as_of(
        cfg.corpus_as_of, EMBEDDERS[cfg.index_embedder]
    )
    # Chapter 12: the help centre's versions in force, for freshness.
    in_force = {a.id: a.version for a in snapshot()}
    retriever = CheckedRetriever(
        index, EMBEDDERS[cfg.query_embedder], in_force, slis
    )
    limit = cfg.agent_max_steps
    linnet = Linnet(retriever, guard=lambda: LoopGuard(limit))
    guardrail = Guardrail(cfg.guardrail_version)
    screened = Screened(linnet, guardrail, slis)
    # Chapter 13: a sample of answers evaluated in process.
    judges = standard()
    results = results if results is not None else ResultEmitter()

    def versions() -> tuple[str, str]:
        used: Prompt = vars(running)["SUPPORT"]  # as Linnet reads it
        return used.version, index.version

    evaluating = Evaluating(
        screened, judges, results, cfg.evaluation_rate, versions
    )
    answer, stream_answer = (
        evaluating.answer,
        evaluating.stream_answer,
    )
    vault = None
    if cfg.content_capture == "vault":
        vault = Vault(cfg.vault_path, cfg.vault_ttl_s)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        slis.start()  # after instrument(): the meter is real by now
        results.start(judges, *versions())
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

    @app.post("/outcome", status_code=204)
    def outcome(body: OutcomeIn) -> None:
        """Chapter 12: how a conversation ended, from the help desk.
        Nothing in it identifies the customer."""
        slis.outcome(body.escalated)

    @app.exception_handler(LimitExceeded)
    async def over_limit(
        _: Request, err: LimitExceeded
    ) -> JSONResponse:
        """Chapter 11: refused before any model call was made."""
        LOG.warning("chat refused: spend limit")
        wait = str(math.ceil(err.retry_after))
        return JSONResponse(
            {"detail": "Linnet cannot answer now."},
            status_code=429,
            headers={"Retry-After": wait},
        )

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
            index_version=index.version,
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
        SPEND.set(Spend(cfg.tenant))  # Chapter 11: this answer's bill
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
            with deadline(cfg.deadline_s):  # Chapter 16
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
