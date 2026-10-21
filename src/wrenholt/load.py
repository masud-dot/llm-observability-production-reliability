"""A deterministic load generator (Chapter 18).

    times = impulse(30, 120, at=40, width=10, seconds=120)
    shots = asyncio.run(drive(times, call))

A pattern is a rate in requests a second over time. Its arrivals are
where the running count of expected requests passes each whole
number, so a pattern always gives the same times. drive() starts
each call at its time without waiting for the calls before it, as
real traffic does, and records when each started and ended.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

Rate = Callable[[float], float]


def arrivals(
    rate: Rate, seconds: float, step: float = 0.001
) -> list[float]:
    out: list[float] = []
    expected = 0.0
    for i in range(round(seconds / step)):
        t = i * step
        expected += rate(t + step / 2) * step  # midpoint
        while expected >= len(out) + 1 - 1e-9:
            out.append(round(t, 3))
    return out


def gradual(start: float, end: float, seconds: float) -> list[float]:
    """A rate rising in a straight line from start to end."""
    return arrivals(
        lambda t: start + (end - start) * t / seconds, seconds
    )


def impulse(
    base: float, peak: float, at: float, width: float, seconds: float
) -> list[float]:
    """base a second, and peak from at for width seconds."""
    return arrivals(
        lambda t: peak if at <= t < at + width else base, seconds
    )


@dataclass(frozen=True)
class Shot[T]:
    index: int
    start: float  # seconds after the first arrival
    end: float
    result: T | Exception


async def drive[T](
    times: Sequence[float],
    call: Callable[[int], Awaitable[T]],
    clock: Callable[[], float] = time.monotonic,
) -> list[Shot[T]]:
    origin, shots = clock(), list[Shot[T]]()

    async def one(i: int) -> None:
        start = clock() - origin
        result: T | Exception
        try:
            result = await call(i)
        except Exception as err:  # the experiment records it
            result = err
        shots.append(Shot(i, start, clock() - origin, result))

    tasks = []
    for i, at in enumerate(times):
        if (wait := origin + at - clock()) > 0:
            await asyncio.sleep(wait)
        tasks.append(asyncio.create_task(one(i)))
    await asyncio.gather(*tasks)
    return sorted(shots, key=lambda s: s.index)
