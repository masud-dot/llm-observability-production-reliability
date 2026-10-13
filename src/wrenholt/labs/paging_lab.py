"""FS-02 and FS-03 against the burn-rate alerts (Chapter 14).

A minute-by-minute model of Wrenholt's traffic after three days of
it: the normal hour's 120 answers, 90 of them interactive, or ten
answers an hour for the low-traffic rows. Each minute the model
counts good and bad events over every window exactly and asks each
tier what its alert asks. Prometheus counts the same windows from
samples; tests/slo/slo_alerts.test.yaml shows it firing in the same
minutes, and resetting a minute sooner. SIMULATED throughout.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import accumulate

from wrenholt.labs.fs12_lab import HOUR
from wrenholt.slo.alerts import MIN_BAD, Tier, tiers_for
from wrenholt.slo.objectives import Slo, load_objectives

HISTORY = 3 * 24 * 60  # minutes of normal traffic before a fault
HORIZON = 12 * 60  # minutes watched after it starts
WINDOW = 28 * 24 * 60  # the SLO window, in minutes
MINUTES = {"5m": 5, "30m": 30, "1h": 60, "6h": 360, "3d": 4320}
ANSWERS = Fraction(HOUR.total(), 60)  # 2 a minute
INTERACTIVE = ANSWERS - Fraction(HOUR["refund_request"], 60)

Events = Callable[[int], Fraction]


def steady(rate: Fraction) -> Events:
    return lambda _: rate


def every(minutes: int) -> Events:
    """One answer every few minutes, the first in minute 1."""
    return lambda m: Fraction(1) if m % minutes == 1 else Fraction(0)


@dataclass(frozen=True)
class Scenario:
    name: str
    slo: str
    valid: Events
    fault: int  # minutes of fault, from minute 1
    only: int = 0  # bad events allowed in all, when not every one

    def bad(self, m: int) -> Fraction:
        if not 1 <= m <= self.fault:
            return Fraction(0)
        return self.valid(m)


SCENARIOS = (
    Scenario(
        "FS-03, 30 minutes", "availability", steady(ANSWERS), 30
    ),
    Scenario(
        "FS-02, 2 hours", "ttfc_interactive", steady(INTERACTIVE), 120
    ),
    Scenario(
        "FS-02, 5 minutes", "ttfc_interactive", steady(INTERACTIVE), 5
    ),
    Scenario("FS-03, 5 minutes", "availability", steady(ANSWERS), 5),
    Scenario("one failure, 10/h", "availability", every(6), 1),
    Scenario("FS-03 at 10/h, 2 h", "availability", every(6), 120),
)


@dataclass
class Outcome:
    fired: dict[str, int | None] = field(default_factory=dict)
    reset: dict[str, int | None] = field(default_factory=dict)
    at_page: Fraction | None = None  # budget spent by the page
    episode: Fraction = Fraction(0)  # budget the fault spent
    short_alone: int | None = None  # the 5-minute window by itself


def tier_name(t: Tier) -> str:
    return f"{t.severity} {t.long}"


class Counts:
    """Prefix sums of valid and bad events, minute by minute."""

    def __init__(self, sc: Scenario) -> None:
        span = range(-HISTORY + 1, HORIZON + 1)
        self.first = span.start
        self.valid = [
            Fraction(0),
            *accumulate(sc.valid(m) for m in span),
        ]
        self.bad = [Fraction(0), *accumulate(sc.bad(m) for m in span)]

    def window(
        self, m: int, minutes: int
    ) -> tuple[Fraction, Fraction]:
        """Bad and valid events in the minutes (m - minutes, m]."""
        end = m - self.first + 1
        start = end - minutes
        return (
            self.bad[end] - self.bad[start],
            self.valid[end] - self.valid[start],
        )


def burning(c: Counts, s: Slo, t: Tier, m: int) -> bool:
    """What the tier's alert asks, of exact counts."""
    limit = Fraction(t.burn * s.budget)
    bad, valid = c.window(m, MINUTES[t.long])
    short_bad, short_valid = c.window(m, MINUTES[t.short])
    if not valid or not short_valid:
        return False
    over = bad / valid > limit and short_bad / short_valid > limit
    if t.severity == "page":
        return over and bad >= MIN_BAD
    return over


def run(sc: Scenario) -> Outcome:
    s = load_objectives().get(sc.slo)
    c = Counts(sc)
    out = Outcome()
    fast = tiers_for(s)[0]
    for t in tiers_for(s):
        on = [m for m in range(1, HORIZON + 1) if burning(c, s, t, m)]
        out.fired[tier_name(t)] = on[0] if on else None
        after = [
            m
            for m in range(sc.fault + 1, HORIZON + 1)
            if not burning(c, s, t, m)
        ]
        out.reset[tier_name(t)] = (
            after[0] - sc.fault if on and after else None
        )
    limit = Fraction(fast.burn * s.budget)
    for m in range(1, HORIZON + 1):
        bad, valid = c.window(m, 5)
        if valid and bad / valid > limit:
            out.short_alone = m
            break
    allowed = Fraction(s.budget) * sum(
        sc.valid(m) for m in range(1, WINDOW + 1)
    )
    pages = [v for k, v in out.fired.items() if k.startswith("page")]
    first = min((p for p in pages if p is not None), default=None)
    if first is not None:
        spent = sum(sc.bad(m) for m in range(1, first + 1))
        out.at_page = spent / allowed
    out.episode = sum(sc.bad(m) for m in range(1, sc.fault + 1)) / (
        allowed
    )
    return out


def ratios(
    sc: Scenario, minutes: int
) -> list[tuple[int, float, float]]:
    """The 1-hour and 5-minute error ratios each minute, for the
    figure."""
    c = Counts(sc)
    rows = []
    for m in range(-10, minutes + 1):
        bad, valid = c.window(m, 60)
        short_bad, short_valid = c.window(m, 5)
        rows.append(
            (m, float(bad / valid), float(short_bad / short_valid))
        )
    return rows


def cell(minute: int | None) -> str:
    return "-" if minute is None else str(minute)


def share(f: Fraction | None) -> str:
    return "-" if f is None else f"{float(f):.1%}"


def main() -> None:
    print("FS-02 and FS-03 against the alerts (SIMULATED)")
    print("minutes until each alert fires; budget is the 28-day one")
    head = ("", "page 1h", "page 6h", "ticket", "at page", "in all")
    print(f"{head[0]:<20}" + "".join(f"{h:>8}" for h in head[1:]))
    outcomes = {sc.name: run(sc) for sc in SCENARIOS}
    for name, o in outcomes.items():
        fired = [o.fired.get(k) for k in ("page 1h", "page 6h")]
        fired.append(o.fired["ticket 3d"])
        cells = [cell(f) for f in fired]
        cells += [share(o.at_page), share(o.episode)]
        print(f"{name:<20}" + "".join(f"{x:>8}" for x in cells))
    alone = sum(o.short_alone is not None for o in outcomes.values())
    print(f"the 5-minute window alone pages on {alone} of 6")
    reset = outcomes["FS-03, 30 minutes"].reset
    print(
        "reset after FS-03 ends: "
        + ", ".join(f"{k} {v}" for k, v in reset.items())
        + " min"
    )
