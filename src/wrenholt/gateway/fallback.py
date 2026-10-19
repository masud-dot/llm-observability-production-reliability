"""Fallback chains (Chapter 17).

FallbackGateway gives a model a chain of others. A call that fails
with a provider's own failure, or that a breaker or a bulkhead
refuses, goes to the next model in the chain, within the same
deadline and retry budget. Every call tries the model asked for
first, so a fallback ends by itself when the provider recovers. One
call in `every` goes to the first fallback first, to exercise it; if
the fallback fails there, the model asked for answers. Each switch
is a wrenholt.fallback event on the caller's span, and the caller's
span records how its answer was made, and why.
"""

import itertools
from collections.abc import Mapping, Sequence
from decimal import Decimal
from enum import StrEnum
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span

from wrenholt.gateway.cost import PriceTable
from wrenholt.gateway.errors import ErrorType, ProviderError, Rejected
from wrenholt.gateway.guarded import GuardedGateway
from wrenholt.gateway.types import Completion, Message
from wrenholt.telemetry import conventions as c

FALL_BACK_ON = frozenset(
    {
        ErrorType.PROVIDER_UNAVAILABLE,
        ErrorType.OVERLOADED,
        ErrorType.TIMEOUT,
        ErrorType.RATE_LIMITED,
        ErrorType.QUOTA_EXHAUSTED,
    }
)


class Mode(StrEnum):
    FULL = "full"
    FALLBACK = "fallback_model"
    CACHED = "cached"
    CITATION = "citation_only"
    HANDOFF = "handoff"
    REFUSED = "refused"


def mark(span: Span, mode: Mode, reason: str) -> None:
    span.set_attributes(
        {c.DEGRADED_MODE: mode.value, c.DEGRADED_REASON: reason}
    )


def ratio(prices: PriceTable, primary: str, fallback: str) -> Decimal:
    """The fallback's dearest token kind, in multiples of the
    primary's price for it."""
    a, b = prices.prices[primary], prices.prices[fallback]
    return max(
        b.input / a.input,
        b.cached_input / a.cached_input,
        b.output / a.output,
    )


def affordable(
    prices: PriceTable,
    primary: str,
    fallback: str,
    peak_per_hour: Decimal,
    limit: Decimal,
) -> bool:
    """The planning peak, at the fallback's prices, stays under the
    tenant's hourly spend limit (Chapter 11)."""
    return peak_per_hour * ratio(prices, primary, fallback) < limit


def moves(err: ProviderError) -> bool:
    """A failure another provider may not share. A spent deadline
    is spent for every provider."""
    if isinstance(err, Rejected) and err.reason == "deadline":
        return False
    return err.error_type in FALL_BACK_ON


class FallbackGateway(GuardedGateway):
    def __init__(
        self,
        *args: Any,
        chains: Mapping[str, Sequence[str]] | None = None,
        every: int = 100,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.chains = {m: tuple(f) for m, f in (chains or {}).items()}
        self.every = every
        self._count = itertools.count(1)  # shared with tool views

    async def chat(
        self, model: str, messages: Sequence[Message]
    ) -> Completion:
        chain = self.chains.get(model, ())
        span = trace.get_current_span()
        order, reason = [model, *chain], ""
        if (
            chain
            and self.every
            and next(self._count) % self.every == 0
        ):
            order, reason = [chain[0], model, *chain[1:]], "exercise"
        for i, tried in enumerate(order):
            try:
                done = await super().chat(tried, messages)
            except ProviderError as err:
                exercised = reason == "exercise" and i == 0
                if i == len(order) - 1 or not (
                    exercised or moves(err)
                ):
                    raise
                span.add_event(
                    c.FALLBACK_EVENT,
                    {
                        c.FALLBACK_FROM: tried,
                        c.FALLBACK_TO: order[i + 1],
                        c.ERROR_TYPE: err.error_type.value,
                    },
                )
                reason = reason or err.error_type.value
                continue
            if reason:
                mode = Mode.FULL if tried == model else Mode.FALLBACK
                mark(span, mode, reason)
            return done
        raise AssertionError("unreachable")
