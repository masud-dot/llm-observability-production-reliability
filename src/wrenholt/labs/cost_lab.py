"""Shared harness for Chapter 11's labs (SIMULATED workloads).

Linnet answers one question of each journey through a gateway with
the price table, against the mock provider and the orders service.
A first answer warms the provider's prompt cache and is left out, so
every measured call reads the system prompt from the cache, as
calls do all day. Each journey's bill is that answer's Spend.
"""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from opentelemetry.sdk.trace import ReadableSpan

from services.orders.store import OrderStore, generate_orders
from wrenholt.gateway import SPEND, Gateway, Route, Spend, load_prices
from wrenholt.labs.agent_lab import (
    EMBED_1,
    Setup,
    Telemetry,
    services,
)
from wrenholt.orchestrator import linnet
from wrenholt.orchestrator.prompts import SUPPORT, Prompt
from wrenholt.rag.corpus import TODAY
from wrenholt.rag.index import index_as_of
from wrenholt.rag.retriever import Retriever
from wrenholt.tools.orders import OrdersClient

MODEL = "mock-a-fast"
CAP = 512  # Settings().max_output_tokens
QUESTIONS = {
    "policy_question": "How long do I have to return an item?",
    "order_status": "Where is my order WG-100006?",
    "refund_request": "Please refund £5.00 on order WG-100006.",
}
# FS-12: version 2 asks for thorough answers instead of brief ones.
V2 = Prompt(
    SUPPORT.name, "2", SUPPORT.text.replace("briefly", "thoroughly")
)


@dataclass
class Measured:
    spend: dict[str, Spend]  # each journey's bill
    calls: dict[str, list[ReadableSpan]]  # its chat spans, in order
    texts: dict[str, str]  # its answer
    telemetry: Telemetry


@contextmanager
def deployed(prompt: Prompt) -> Iterator[None]:
    """Linnet's prompt, swapped the way a deploy would swap it."""
    names = vars(linnet)
    before = names["SUPPORT"]
    names["SUPPORT"] = prompt
    try:
        yield
    finally:
        names["SUPPORT"] = before


def measure(model: str = MODEL, prompt: Prompt = SUPPORT) -> Measured:
    t = Telemetry()
    store = OrderStore(generate_orders())
    retriever = Retriever(
        index_as_of(TODAY, EMBED_1),
        EMBED_1,
        tracer_provider=t.tracing,
        meter_provider=t.meters,
    )
    agent = linnet.Linnet(
        retriever, tracer_provider=t.tracing, meter_provider=t.meters
    )
    found = Measured({}, {}, {}, t)

    async def go(provider: str, orders_url: str) -> None:
        route = Route("wrenholt.mock_a", provider, "sk-mock")
        gw = Gateway(
            {model: route},
            tracer_provider=t.tracing,
            meter_provider=t.meters,
            prices=load_prices(),
            max_tokens={model: CAP},
        )
        orders = OrdersClient(orders_url)
        try:
            warm = QUESTIONS["policy_question"]
            await agent.answer(gw, model, warm, orders)
            for journey, question in QUESTIONS.items():
                before = len(t.named("chat "))
                bill = found.spend[journey] = Spend("wrenholt")
                SPEND.set(bill)
                done = await agent.answer(gw, model, question, orders)
                found.calls[journey] = t.named("chat ")[before:]
                found.texts[journey] = done.text
        finally:
            await orders.aclose()
            await gw.aclose()

    with (
        services(Setup(), store) as (provider, orders_url),
        deployed(prompt),
    ):
        asyncio.run(go(provider, orders_url))
    return found
