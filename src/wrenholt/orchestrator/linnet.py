"""Linnet's answer path through the gateway (Chapters 4, 6 and 8).

Same prompt as the baseline, now versioned; an order mentioned in
the question is looked up first, and only its status and date
reach the model.
"""

from collections.abc import AsyncGenerator
from contextlib import aclosing
from dataclasses import dataclass

from wrenholt.gateway import (
    Completion,
    Gateway,
    Message,
    StreamResult,
)
from wrenholt.gateway.context import prompt
from wrenholt.orchestrator.prompts import SUPPORT
from wrenholt.tools.orders import ORDER_ID, OrdersClient


@dataclass(frozen=True)
class Answer:
    text: str
    completion: Completion


async def messages_for(
    question: str, orders: OrdersClient | None
) -> list[Message]:
    """The prompt, the order facts if an order is mentioned, and
    the question: the same for whole and streamed answers."""
    messages = [Message("system", SUPPORT.text)]
    found = ORDER_ID.search(question)
    if orders is not None and found:
        facts = await orders.lookup(found.group())
        if facts is not None:
            note = f"Order {facts.order_id}: {facts.status}"
            note += f", placed on {facts.placed_on}."
            messages.append(Message("system", note))
    messages.append(Message("user", question))
    return messages


async def answer(
    gateway: Gateway,
    model: str,
    question: str,
    orders: OrdersClient | None = None,
) -> Answer:
    messages = await messages_for(question, orders)
    with prompt(SUPPORT.name, SUPPORT.version):
        completion = await gateway.chat(model, messages)
    return Answer(completion.text, completion)


async def stream_answer(
    gateway: Gateway,
    model: str,
    question: str,
    orders: OrdersClient | None,
    result: StreamResult,
) -> AsyncGenerator[str]:
    """The same answer, streamed (Chapter 8). The prompt is passed
    to the gateway, not set in a context variable: a generator would
    hold that variable across every yield, into its caller."""
    messages = await messages_for(question, orders)
    used = (SUPPORT.name, SUPPORT.version)
    stream = gateway.stream(model, messages, used, result)
    async with aclosing(stream) as chunks:
        async for piece in chunks:
            yield piece
