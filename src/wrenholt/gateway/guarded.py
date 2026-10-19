"""The gateway with its protective controls (Chapter 16).

GuardedGateway keeps Chapter 4's retry loop and adds, for each
provider, a circuit breaker and a concurrency limit, and for every
attempt a timeout cut to the request's deadline. Its policy should
be a GuardedPolicy, which decides each retry under the deadline and
the retry budget. A refusal is a Rejected error, raised before any
provider call and never retried; the policy records it on the chat
span with every other decision.
"""

import asyncio
import time
from collections.abc import Sequence
from typing import Any

from opentelemetry import trace

from wrenholt.gateway.breaker import Breaker
from wrenholt.gateway.client import Gateway
from wrenholt.gateway.deadlines import Clock, remaining
from wrenholt.gateway.errors import ErrorType, ProviderError, Rejected
from wrenholt.gateway.limits import ConcurrencyLimit
from wrenholt.gateway.openai_compat import OpenAICompatible
from wrenholt.gateway.routing import Route
from wrenholt.gateway.types import Completion, Message
from wrenholt.telemetry import conventions as c


class Bounded(OpenAICompatible):
    """An adapter whose calls also end at the request's deadline."""

    async def chat(
        self, model: str, messages: Sequence[Message]
    ) -> Completion:
        left = remaining()
        if left is None:
            return await super().chat(model, messages)
        try:
            async with asyncio.timeout(left):
                return await super().chat(model, messages)
        except TimeoutError:
            raise ProviderError(ErrorType.TIMEOUT) from None


class GuardedGateway(Gateway):
    def __init__(
        self,
        *args: Any,
        attempt_timeout_s: float = 30.0,
        in_flight: int = 64,
        failures: int = 5,
        cool_down_s: float = 30.0,
        clock: Clock = time.monotonic,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._adapters = {
            r: Bounded(r, attempt_timeout_s, self._caps)
            for r in self._adapters
        }
        providers = {r.provider for r in self._adapters}
        self.breakers = {
            p: Breaker(p, failures, cool_down_s, clock)
            for p in providers
        }
        self.limits = {
            p: ConcurrencyLimit(in_flight) for p in providers
        }

    async def _attempt(
        self,
        route: Route,
        model: str,
        messages: Sequence[Message],
        number: int,
        delay: float,
    ) -> Completion:
        span = trace.get_current_span()
        left = remaining()
        if left is not None:
            span.set_attribute(c.DEADLINE_LEFT, round(left, 3))
            if left <= 0:
                raise Rejected(ErrorType.TIMEOUT, "deadline")
        breaker = self.breakers[route.provider]
        limit = self.limits[route.provider]
        if not breaker.allow():
            raise Rejected(
                ErrorType.PROVIDER_UNAVAILABLE, "breaker_open"
            )
        span.set_attribute(c.LIMIT_IN_FLIGHT, limit.in_flight)
        if not limit.acquire():
            breaker.cancelled()
            raise Rejected(ErrorType.OVERLOADED, "limit_full")
        try:
            result = await super()._attempt(
                route, model, messages, number, delay
            )
        except ProviderError as err:
            breaker.record(err.error_type)
            raise
        except BaseException:
            breaker.cancelled()
            raise
        finally:
            limit.release()
        breaker.record(None)
        return result
