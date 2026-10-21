"""Protective controls (Chapter 16): properties of the backoff, the
deadline and the budget, and the breaker's states."""

import math

from hypothesis import given
from hypothesis import strategies as st

from wrenholt.gateway.breaker import Breaker, State
from wrenholt.gateway.deadlines import DEADLINE
from wrenholt.gateway.errors import ErrorType, ProviderError
from wrenholt.gateway.retry import GuardedPolicy, RetryBudget
from wrenholt.labs.protect_lab import FakeClock

RETRYABLE = st.sampled_from(
    [
        ErrorType.RATE_LIMITED,
        ErrorType.OVERLOADED,
        ErrorType.PROVIDER_UNAVAILABLE,
        ErrorType.TIMEOUT,
    ]
)
DOWN = ErrorType.PROVIDER_UNAVAILABLE


def state(b: Breaker) -> State:
    """Read afresh: mypy keeps a narrowed attribute across calls."""
    return b.state


@given(st.integers(1, 10), st.floats(0, 1), RETRYABLE)
def test_backoff_stays_in_its_bounds(
    attempt: int, jitter: float, kind: ErrorType
) -> None:
    p = GuardedPolicy()
    decision, wait = p.decide(attempt, ProviderError(kind), jitter)
    if attempt >= p.max_attempts:
        assert (decision, wait) == ("attempts_spent", None)
        return
    full = min(p.max_delay, p.base_delay * 2 ** (attempt - 1))
    assert decision == "retry" and wait is not None
    assert 0.75 * full <= wait <= full <= p.max_delay


@given(
    st.floats(0, 30),
    st.none() | st.floats(0, 30),
    st.integers(1, 2),
    st.floats(0, 1),
)
def test_no_retry_waits_past_the_deadline(
    left: float, after: float | None, attempt: int, jitter: float
) -> None:
    p = GuardedPolicy(None, FakeClock())  # the clock reads 0
    err = ProviderError(ErrorType.RATE_LIMITED, 429, after)
    token = DEADLINE.set(left)
    try:
        decision, wait = p.decide(attempt, err, jitter)
    finally:
        DEADLINE.reset(token)
    if decision == "retry":
        assert wait is not None and 0 <= wait < left
    else:
        assert (decision, wait) == ("deadline", None)


@given(st.lists(st.floats(0, 300), max_size=150), st.integers(0, 12))
def test_the_budget_grants_exactly_its_minute(
    times: list[float], per_minute: int
) -> None:
    clock = FakeClock()
    budget = RetryBudget(per_minute, clock)
    granted: list[float] = []
    for t in sorted(times):
        clock.now = t
        took = budget.spend()
        window = sum(t - 60 < g <= t for g in granted)
        assert took == (window < per_minute)
        if took:
            granted.append(t)


def test_the_breaker_opens_probes_and_closes() -> None:
    clock = FakeClock()
    b = Breaker("wrenholt.mock_a", clock=clock)
    for _ in range(4):
        assert b.allow()
        b.record(DOWN)
    assert state(b) is State.CLOSED
    assert b.allow()
    b.record(ErrorType.TIMEOUT)  # the fifth in a row
    assert state(b) is State.OPEN
    clock.now = 29.9
    assert not b.allow()
    clock.now = 30.0
    assert b.allow() and state(b) is State.HALF_OPEN
    assert not b.allow()  # one probe at a time
    b.record(ErrorType.OVERLOADED)
    assert state(b) is State.OPEN
    clock.now = 60.0
    assert b.allow()
    b.cancelled()  # a probe without an outcome frees the slot
    assert b.allow()
    b.record(None)
    assert state(b) is State.CLOSED and b.allow()


def test_only_the_providers_own_failures_count() -> None:
    b = Breaker("wrenholt.mock_a", clock=FakeClock())
    others = [
        ErrorType.RATE_LIMITED,
        ErrorType.QUOTA_EXHAUSTED,
        ErrorType.INVALID_REQUEST,
    ]
    for kind in others * 5 + [DOWN] * 4 + [None] + [DOWN] * 4:
        assert b.allow()
        b.record(kind)  # a success resets the count
    assert state(b) is State.CLOSED


STEPS = st.lists(
    st.tuples(
        st.floats(0, 20),
        st.sampled_from([None, DOWN, ErrorType.RATE_LIMITED]),
    ),
    max_size=80,
)


@given(STEPS)
def test_an_open_breaker_waits_and_probes_once(
    steps: list[tuple[float, ErrorType | None]],
) -> None:
    clock = FakeClock()
    b = Breaker("wrenholt.mock_a", clock=clock)
    opened = -math.inf
    for dt, outcome in steps:
        clock.now += dt
        before = state(b)
        allowed = b.allow()
        if before is State.OPEN and clock.now - opened < 30:
            assert not allowed and state(b) is State.OPEN
        if not allowed:
            continue
        if state(b) is State.HALF_OPEN:
            assert not b.allow()
        b.record(outcome)
        if state(b) is State.OPEN:
            opened = clock.now
