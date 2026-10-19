"""Fallbacks, degraded answers and shedding (Chapter 17,
SIMULATED).

    uv run python scripts/fallback_lab.py

The fake clock, the peak rate and the deadline are Chapter 16's lab;
the decisions are the gateway's own classes. FS-03 runs with
provider B as the fallback, and with a fallback broken since it was
configured. FS-13 prices each candidate fallback at the planning
peak. FS-16's sale day doubles the traffic against room for 45
answers a second, with a queue and with admission control.
"""

import heapq
import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal

from wrenholt.api.admission import Admission
from wrenholt.diagnosis import quantile
from wrenholt.gateway import load_prices
from wrenholt.gateway.breaker import Breaker
from wrenholt.gateway.deadlines import DEADLINE
from wrenholt.gateway.errors import ErrorType, ProviderError, Rejected
from wrenholt.gateway.fallback import affordable, moves, ratio
from wrenholt.gateway.retry import GuardedPolicy, RetryBudget
from wrenholt.labs.protect_lab import (
    DEADLINE_S,
    RATE,
    SEED,
    FakeClock,
    outage,
)

A, B, LARGE = "mock-a-fast", "mock-b-standard", "mock-a-large"
LIMIT = Decimal("60.00")  # Settings().spend_per_hour
Fault = Callable[[float], ProviderError | None]


def healthy(now: float) -> ProviderError | None:
    return None


def retired(now: float) -> ProviderError | None:
    """A fallback whose model the provider no longer serves."""
    return ProviderError(ErrorType.INVALID_REQUEST, 404)


@dataclass
class Run:
    answers: int = 0
    failed: int = 0
    calls: Counter[str] = field(default_factory=Counter)
    served: Counter[str] = field(default_factory=Counter)
    exercised: int = 0
    exercise_failed: int = 0
    back: float | None = None  # A's first answer after it failed


def fs03(
    seconds: float,
    faults: dict[str, Fault],
    every: int = 100,
    chain: tuple[str, ...] = (A, B),
) -> Run:
    clock, run = FakeClock(), Run()
    policy = GuardedPolicy(RetryBudget(60, clock), clock)
    breakers = {m: Breaker(m, clock=clock) for m in chain}
    jitter = random.Random(SEED)
    queue: list[tuple[float, int, int, int]] = []
    orders: dict[int, tuple[str, ...]] = {}
    for i in range(round(seconds * RATE)):
        exercise = len(chain) > 1 and every and (i + 1) % every == 0
        orders[i] = (chain[1], chain[0]) if exercise else chain
        heapq.heappush(queue, (i / RATE, i, 0, 1))
    a_failed = False
    while queue:
        now, request, k, attempt = heapq.heappop(queue)
        clock.now = now
        order = orders[request]
        model, exercise = order[k], order != chain
        run.answers += k == 0 and attempt == 1
        err: ProviderError | None
        if not breakers[model].allow():
            err = Rejected(
                ErrorType.PROVIDER_UNAVAILABLE, "breaker_open"
            )
        else:
            run.calls[model] += 1
            err = faults[model](now)
            breakers[model].record(err.error_type if err else None)
        if exercise and k == 0:
            run.exercised += attempt == 1
            run.exercise_failed += err is not None and attempt == 1
        if err is None:
            run.served[model] += 1
            if model == A and a_failed and run.back is None:
                run.back = now
            continue
        a_failed = a_failed or model == A
        token = DEADLINE.set(request / RATE + DEADLINE_S)
        decision, wait = policy.decide(attempt, err, jitter.random())
        DEADLINE.reset(token)
        last = k == len(order) - 1
        if wait is not None and not (exercise and k == 0):
            heapq.heappush(
                queue, (now + wait, request, k, attempt + 1)
            )
        elif not last and (exercise and k == 0 or moves(err)):
            heapq.heappush(queue, (now, request, k + 1, 1))
        else:
            run.failed += 1
    return run


def fs03_runs() -> dict[str, Run]:
    down = outage(100)
    return {
        "no fallback": fs03(130, {A: down}, chain=(A,)),
        "fallback B": fs03(130, {A: down, B: healthy}),
        "B retired": fs03(130, {A: down, B: retired}, every=0),
        "B retired, 1%": fs03(60, {A: healthy, B: retired}),
    }


def fs13() -> list[tuple[str, Decimal, Decimal, bool]]:
    """Each candidate fallback at Chapter 11's planning peak."""
    from wrenholt.labs.fs13_lab import run  # runs the mock

    prices, peak = load_prices(), run(A).peak
    return [
        (
            model,
            ratio(prices, A, model),
            peak * ratio(prices, A, model),
            affordable(prices, A, model, peak, LIMIT),
        )
        for model in (B, LARGE)
    ]


@dataclass(frozen=True)
class Surge:
    full: int  # answered by the model within the deadline
    degraded: int  # answered without a model, at once
    failed: int  # timed out in the queue, or refused
    refunds_failed: int
    p95_s: float  # full answers, arrival to answer


def surge(
    admit: bool, seconds: float = 120, rate: float = 80
) -> Surge:
    """FS-16: twice the planning peak, one question in four a
    refund, 2 s an answer, room for 90 at once (45 a second)."""
    service, slots, reserved = 2.0, 90, 18
    free = [0.0] * slots  # when each slot is next free (queue)
    admission, ends = Admission(slots, reserved), list[float]()
    full: list[float] = []
    degraded = failed = refunds = 0
    for i in range(round(seconds * rate)):
        now = i / rate
        critical = i % 4 == 3
        if admit:
            while ends and ends[0] <= now:
                heapq.heappop(ends)
                admission.release()
            cls = "critical_action" if critical else "interactive"
            if admission.admit(cls):
                heapq.heappush(ends, now + service)
                full.append(service)
            elif critical:
                failed += 1  # 503 with Retry-After
                refunds += 1
            else:
                degraded += 1
            continue
        start = max(now, free[0])
        if start + service > now + DEADLINE_S:
            failed += 1  # its deadline passes in the queue
            refunds += critical
            continue
        heapq.heapreplace(free, start + service)
        full.append(start + service - now)
    p95 = quantile(sorted(full), 0.95)
    return Surge(len(full), degraded, failed, refunds, round(p95, 2))


def report() -> list[str]:
    runs = fs03_runs()
    lines = [
        "FS-03, a 100 s outage of A in 130 s of traffic:",
        f"{'':16}answers  failed  calls A  calls B  A again",
    ]
    for name in ("no fallback", "fallback B", "B retired"):
        r = runs[name]
        back = f"{r.back:.1f} s" if r.back is not None else "-"
        lines.append(
            f"  {name:<14}{r.answers:>7,}{r.failed:>8,}"
            f"{r.calls[A]:>9,}{r.calls[B]:>9,}{back:>9}"
        )
    r = runs["B retired, 1%"]
    lines.append(
        f"  B retired, 1 in 100 exercised, a healthy minute:"
        f" {r.exercise_failed} of {r.exercised} failed"
    )
    lines.append(f"    and {r.failed} answers failed")
    lines.append("FS-13, each fallback at the planning peak:")
    for model, times, cost, ok in fs13():
        verdict = "allowed" if ok else "refused at start-up"
        lines.append(
            f"  {model:<16}{times:>4} x price: ${cost:.2f} an hour,"
            f" {verdict}"
        )
    lines += [
        "FS-16, sale day: 80 a second, room for 45 a second:",
        f"{'':14}full  p95 s  degraded  failed  refunds",
    ]
    for name, admit in (("queue", False), ("admission", True)):
        s = surge(admit)
        lines.append(
            f"  {name:<10}{s.full:>6,}{s.p95_s:>7.2f}"
            f"{s.degraded:>10,}{s.failed:>8,}{s.refunds_failed:>9,}"
        )
    return lines


def main() -> int:
    print("\n".join(report()))
    return 0
