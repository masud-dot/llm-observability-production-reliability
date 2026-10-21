"""The gateway's protective controls under load (Chapter 16,
SIMULATED).

    uv run python scripts/protect_lab.py

A fake clock and a scripted provider stand in for time and the
network; the decisions are made by the gateway's own classes,
GuardedPolicy, RetryBudget, Breaker and ConcurrencyLimit, as
GuardedGateway uses them. Requests arrive at the peak of Chapter
12's planning hour, 40 a second, each with a 10 s deadline.
"""

import heapq
import math
import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from wrenholt.diagnosis import quantile
from wrenholt.gateway.breaker import Breaker, State
from wrenholt.gateway.deadlines import DEADLINE
from wrenholt.gateway.errors import ErrorType, ProviderError, Rejected
from wrenholt.gateway.limits import ConcurrencyLimit
from wrenholt.gateway.policy import RetryPolicy
from wrenholt.gateway.retry import GuardedPolicy, RetryBudget
from wrenholt.labs.fs12_lab import PEAK
from wrenholt.slo.rules import promname
from wrenholt.telemetry import conventions as c

RATE = PEAK / 3600  # 40 requests a second
DEADLINE_S = 10.0  # Chapter 2: an answer, end to end
AGENT_S = 7.8  # Chapter 11: the refund journey's agent span
SEED = 16
Fault = Callable[[float], ProviderError | None]


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Quota:
    """FS-01: the provider admits per_second calls in each second
    and answers the rest 429, retry-after 1 s."""

    def __init__(self, per_second: int) -> None:
        self.per_second = per_second
        self.used: Counter[int] = Counter()

    def __call__(self, now: float) -> ProviderError | None:
        if self.used[int(now)] >= self.per_second:
            return ProviderError(ErrorType.RATE_LIMITED, 429, 1.0)
        self.used[int(now)] += 1
        return None


def outage(until: float) -> Fault:
    """FS-03: connections refused until `until`, then service."""

    def fault(now: float) -> ProviderError | None:
        if now < until:
            return ProviderError(ErrorType.PROVIDER_UNAVAILABLE)
        return None

    return fault


@dataclass
class Run:
    requests: int = 0
    calls: int = 0  # calls that reached the provider
    failed: int = 0  # requests that ended in an error
    refused: list[float] = field(default_factory=list)  # by breaker
    per_second: Counter[int] = field(default_factory=Counter)
    decisions: Counter[str] = field(default_factory=Counter)
    states: list[tuple[float, str]] = field(default_factory=list)

    def note(self, now: float, state: State) -> None:
        if not self.states or self.states[-1][1] != state.value:
            self.states.append((now, state.value))


def simulate(
    fault: Fault, seconds: float, *, budget: bool, breaker: bool
) -> Run:
    """Requests for `seconds`; every call meets `fault`."""
    clock = FakeClock()
    spend = RetryBudget(60, clock) if budget else None
    policy = GuardedPolicy(spend, clock)
    b = Breaker("wrenholt.mock_a", clock=clock) if breaker else None
    jitter, run = random.Random(SEED), Run()
    queue = [(i / RATE, i, 1) for i in range(round(seconds * RATE))]
    heapq.heapify(queue)  # (time, request, attempt)
    while queue:
        now, request, attempt = heapq.heappop(queue)
        clock.now = now
        if attempt == 1:
            run.requests += 1
        err: ProviderError | None
        if b is not None and not b.allow():
            err = Rejected(
                ErrorType.PROVIDER_UNAVAILABLE, "breaker_open"
            )
            run.refused.append(now)
        else:
            if b is not None:
                run.note(now, b.state)
            run.calls += 1
            run.per_second[int(now)] += 1
            err = fault(now)
            if b is not None:
                b.record(err.error_type if err else None)
                run.note(now, b.state)
        if err is None:
            continue
        token = DEADLINE.set(request / RATE + DEADLINE_S)
        decision, wait = policy.decide(attempt, err, jitter.random())
        DEADLINE.reset(token)
        run.decisions[decision] += 1
        if wait is None:
            run.failed += 1
        else:
            heapq.heappush(queue, (now + wait, request, attempt + 1))
    return run


def fs01() -> dict[str, Run]:
    """A minute at peak against a quota of 35 calls a second."""
    return {
        name: simulate(Quota(35), 60, budget=budget, breaker=False)
        for name, budget in (("chapter 4", False), ("budget", True))
    }


def fs03() -> dict[str, Run]:
    """100 s of outage inside 130 s of traffic."""
    return {
        name: simulate(outage(100), 130, budget=b, breaker=k)
        for name, b, k in (
            ("chapter 4", False, False),
            ("budget", True, False),
            ("budget+breaker", True, True),
        )
    }


def decisions() -> list[tuple[str, str]]:
    """A 429 with 9 s of the deadline left; FS-18's quota."""
    clock = FakeClock()
    guarded, plain = GuardedPolicy(None, clock), RetryPolicy()
    out = []
    for after in (6.0, 9.5):
        err = ProviderError(ErrorType.RATE_LIMITED, 429, after)
        token = DEADLINE.set(9.0)
        decision, wait = guarded.decide(1, err, 0.0)
        DEADLINE.reset(token)
        old = plain.next_delay(1, err, 0.0)
        shown = (
            decision if wait is None else f"{decision} in {wait} s"
        )
        out.append((f"retry-after {after} s", shown))
        out.append(("  chapter 4", "retry" if old else "stop"))
    quota = ProviderError(ErrorType.QUOTA_EXHAUSTED, 429)
    out.append(("FS-18 quota", guarded.decide(1, quota, 0.0)[0]))
    b = Breaker("wrenholt.mock_a", clock=clock)
    for _ in range(10):
        b.record(ErrorType.QUOTA_EXHAUSTED)
    out.append(("  breaker after 10", b.state.value))
    return out


def timeout(n: int = 100_000) -> dict[str, float]:
    """An attempt timeout from a day of call times: accept 0.1 %
    false timeouts and read the 99.9th percentile."""
    rng = random.Random(SEED)
    day = sorted(
        rng.lognormvariate(math.log(0.4), 0.5) for _ in range(n)
    )
    cut = math.ceil(quantile(day, 0.999) * 10) / 10
    rng = random.Random(SEED + 1)
    later = [rng.lognormvariate(math.log(0.4), 0.5) for _ in range(n)]
    return {
        "p50": quantile(day, 0.5),
        "p99": quantile(day, 0.99),
        "p99.9": quantile(day, 0.999),
        "timeout": cut,
        "false next day": sum(x > cut for x in later) / n,
    }


def bulkhead(
    call_s: float, size: int, seconds: float = 60
) -> tuple[int, int]:
    """Admitted and refused calls of `call_s` each, at RATE."""
    limit, ends = ConcurrencyLimit(size), list[float]()
    admitted = refused = 0
    for i in range(round(seconds * RATE)):
        now = i / RATE
        while ends and ends[0] <= now:
            heapq.heappop(ends)
            limit.release()
        if limit.acquire():
            admitted += 1
            heapq.heappush(ends, now + call_s)
        else:
            refused += 1
    return admitted, refused


QUERY = (
    "histogram_quantile(0.999, sum by (le) (rate("
    f"{promname(c.OPERATION_DURATION, 'bucket')}[1d])))"
)


def report() -> list[str]:
    lines = [
        "FS-01, one minute at peak, quota 35 calls a second:",
        "                  calls  per answer  answers failed",
    ]
    for name, r in fs01().items():
        lines.append(
            f"  {name:<14}{r.calls:>7,}{r.calls / r.requests:>12.2f}"
            f"{r.failed:>16,}"
        )
    lines += [
        "FS-03, a 100 s outage in 130 s of traffic:",
        f"{'':18}calls in outage  answers failed  refused later",
    ]
    for name, r in fs03().items():
        during = sum(n for s, n in r.per_second.items() if s < 100)
        late = sum(t >= 100 for t in r.refused)
        lines.append(
            f"  {name:<14}{during:>17,}{r.failed:>16,}{late:>15,}"
        )
    lines.append("decisions with 9 s of the deadline left:")
    lines += [f"  {k:<20} {v}" for k, v in decisions()]
    t = timeout()
    lines += [
        "attempt timeout from a day of call times:",
        f"  p50 {t['p50']:.2f} s, p99 {t['p99']:.2f} s,"
        f" p99.9 {t['p99.9']:.2f} s: timeout {t['timeout']} s",
        f"  false timeouts the next day: {t['false next day']:.3%}",
        "a bulkhead of 64 at 40 calls a second, one minute:",
    ]
    for call_s in (0.4, 3.0):
        ok, no = bulkhead(call_s, 64)
        lines.append(
            f"  {call_s} s calls: 40 x {call_s} = {RATE * call_s:.0f}"
            f" in flight; {ok:,} admitted, {no:,} refused"
        )
    spare = round(DEADLINE_S - AGENT_S, 1)
    lines.append(
        f"deadline {DEADLINE_S} s - agent span {AGENT_S} s"
        f" = {spare} s"
    )
    return lines


def main() -> int:
    print("\n".join(report()))
    return 0
