"""Request deadlines (Chapter 16).

One deadline per request, set where the request enters and carried
in a context variable to every wait and attempt beneath it. A
nested deadline never extends the one around it, and a retry that
would not finish before it is no retry at all.
"""

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

Clock = Callable[[], float]
DEADLINE: ContextVar[float | None] = ContextVar(
    "deadline", default=None
)


@contextmanager
def deadline(
    seconds: float, clock: Clock = time.monotonic
) -> Iterator[float]:
    end = clock() + seconds
    outer = DEADLINE.get()
    if outer is not None:
        end = min(end, outer)
    token = DEADLINE.set(end)
    try:
        yield end
    finally:
        DEADLINE.reset(token)


def remaining(clock: Clock = time.monotonic) -> float | None:
    """Seconds left before the deadline; None without one."""
    end = DEADLINE.get()
    return None if end is None else max(0.0, end - clock())
