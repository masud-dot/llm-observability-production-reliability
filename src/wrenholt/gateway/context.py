"""Request context the gateway reads (Chapter 6): which prompt the
caller used. Set by the orchestrator around a call. Since Chapter
11, also the bill an answer's calls are charged to."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal

from wrenholt.gateway.types import Usage

PROMPT: ContextVar[tuple[str, str] | None] = ContextVar(
    "wrenholt_prompt", default=None
)


@contextmanager
def prompt(name: str, version: str) -> Iterator[None]:
    token = PROMPT.set((name, version))
    try:
        yield
    finally:
        PROMPT.reset(token)


@dataclass
class Spend:
    """One answer's running bill (Chapter 11): the tenant it is
    charged to, and every call the provider billed for it, a
    retry's or a fallback's included."""

    tenant: str
    cost: Decimal = Decimal(0)
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def charge(self, cost: Decimal, usage: Usage) -> None:
        self.cost += cost
        self.calls += 1
        self.input_tokens += usage.input
        self.output_tokens += usage.output


# Set by the API for each answer. A stream reads it once, at its
# start: it outlives the handler that set it.
SPEND: ContextVar[Spend | None] = ContextVar(
    "wrenholt_spend", default=None
)
