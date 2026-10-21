"""Retries under a deadline and a budget (Chapter 16).

GuardedPolicy keeps Chapter 4's backoff and the provider's
retry-after, and adds two limits. A retry must start before the
request's deadline, which replaces max_retry_after when there is
one. And the process makes at most a fixed number of retries a
minute, the SRE book's server-wide retry budget. Every decision, to
retry or to stop, is an event on the current span.
"""

import time
from collections import deque
from typing import Any

from opentelemetry import trace

from wrenholt.gateway.deadlines import Clock, remaining
from wrenholt.gateway.errors import ProviderError, Rejected
from wrenholt.gateway.policy import RetryPolicy
from wrenholt.telemetry import conventions as c


class RetryBudget:
    """At most per_minute retries in any 60 seconds, process-wide."""

    def __init__(
        self, per_minute: int = 60, clock: Clock = time.monotonic
    ) -> None:
        self.per_minute = per_minute
        self._clock = clock
        self._spent: deque[float] = deque()

    def spend(self) -> bool:
        now = self._clock()
        while self._spent and self._spent[0] <= now - 60:
            self._spent.popleft()
        if len(self._spent) >= self.per_minute:
            return False
        self._spent.append(now)
        return True


class GuardedPolicy(RetryPolicy):
    """Chapter 4's limits are its fields; the budget and the clock
    are not, so a reproduction bundle hashes the same policy."""

    budget: RetryBudget | None
    clock: Clock

    def __init__(
        self,
        budget: RetryBudget | None = None,
        clock: Clock = time.monotonic,
        **limits: Any,
    ) -> None:
        super().__init__(**limits)
        self.budget, self.clock = budget, clock

    def decide(
        self, attempt: int, err: ProviderError, jitter: float
    ) -> tuple[str, float | None]:
        if isinstance(err, Rejected):
            return err.reason, None
        if not err.retryable:
            return "not_retryable", None
        if attempt >= self.max_attempts:
            return "attempts_spent", None
        left = remaining(self.clock)
        wait: float | None
        if err.retry_after is None:
            wait = super().next_delay(attempt, err, jitter)
        elif left is None and err.retry_after > self.max_retry_after:
            wait = None  # Chapter 4's rule, without a deadline
        else:
            wait = err.retry_after
        if wait is None:
            return "too_long", None
        if left is not None and wait >= left:
            return "deadline", None
        if self.budget is not None and not self.budget.spend():
            return "budget_spent", None
        return "retry", wait

    def next_delay(
        self, attempt: int, err: ProviderError, jitter: float
    ) -> float | None:
        decision, wait = self.decide(attempt, err, jitter)
        attrs: dict[str, str | float] = {c.RETRY_DECISION: decision}
        if wait is not None:
            attrs[c.RETRY_WAIT] = round(wait, 3)
        left = remaining(self.clock)
        if left is not None:
            attrs[c.DEADLINE_LEFT] = round(left, 3)
        span = trace.get_current_span()
        span.add_event(c.RETRY_EVENT, attrs)
        span.set_attribute(c.RETRY_DECISION, decision)
        return wait
