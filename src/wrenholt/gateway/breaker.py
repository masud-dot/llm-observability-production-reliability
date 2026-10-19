"""A circuit breaker for each provider (Chapter 16).

Closed: calls pass, and failures in a row are counted; enough of
them open it. Open: calls fail at once, without reaching the
provider, until a cool-down passes. Half-open: one call goes
through as a probe; success closes the breaker, failure opens it
again. Only the provider's own failures count. Every change of
state is an event on the span of the call that caused it.
"""

import time
from enum import StrEnum

from opentelemetry import trace

from wrenholt.gateway.deadlines import Clock
from wrenholt.gateway.errors import ErrorType
from wrenholt.telemetry import conventions as c

COUNTED = frozenset(
    {
        ErrorType.PROVIDER_UNAVAILABLE,
        ErrorType.TIMEOUT,
        ErrorType.OVERLOADED,
    }
)


class State(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class Breaker:
    def __init__(
        self,
        provider: str,
        failures: int = 5,
        cool_down_s: float = 30.0,
        clock: Clock = time.monotonic,
    ) -> None:
        self.provider = provider
        self.threshold, self.cool_down_s = failures, cool_down_s
        self._clock = clock
        self.state = State.CLOSED
        self._failures, self._opened = 0, 0.0
        self._probing = False

    def allow(self) -> bool:
        if self.state is State.OPEN:
            if self._clock() - self._opened < self.cool_down_s:
                return False
            self._move(State.HALF_OPEN)
        if self.state is State.HALF_OPEN:
            if self._probing:
                return False
            self._probing = True
        return True

    def record(self, error: ErrorType | None) -> None:
        """The outcome of a call allow() let through."""
        self._probing = False
        if error is None:
            self._failures = 0
            if self.state is not State.CLOSED:
                self._move(State.CLOSED)
        elif error in COUNTED:
            self._failures += 1
            if (
                self.state is State.HALF_OPEN
                or self._failures >= self.threshold
            ):
                self._opened = self._clock()
                self._move(State.OPEN)

    def cancelled(self) -> None:
        """A call let through ended without an outcome. It says
        nothing about the provider; the next call may probe."""
        self._probing = False

    def _move(self, to: State) -> None:
        trace.get_current_span().add_event(
            c.BREAKER_EVENT,
            {
                c.BREAKER_STATE: to.value,
                c.PROVIDER_NAME: self.provider,
            },
        )
        self.state = to
