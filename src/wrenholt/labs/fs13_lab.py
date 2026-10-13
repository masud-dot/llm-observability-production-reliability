"""FS-13 lab (Chapter 11): a costly fallback (SIMULATED).

    uv run python scripts/fs13_costly_fallback.py

During an incident Linnet was moved from mock-a-fast to
mock-a-large; the incident ended and the setting stayed. Each
journey is answered on both models and priced over FS-09's normal
hour: 120 conversations, 114 of them resolved. The answers, and so
every SLI the book has defined, are the same on both models. The
cost per resolved ticket is not.
"""

from dataclasses import dataclass
from decimal import Decimal

from wrenholt.economics import cost_per_resolved, tickets
from wrenholt.labs.cost_lab import MODEL, measure
from wrenholt.labs.fs12_lab import HOUR, PEAK
from wrenholt.slo.fs09 import normal_hour

FALLBACK = "mock-a-large"
LIMIT = Decimal("60.00")  # Settings().spend_per_hour


@dataclass(frozen=True)
class Run:
    model: str
    per_answer: dict[str, Decimal]
    texts: dict[str, str]

    @property
    def per_resolved(self) -> Decimal:
        return cost_per_resolved(
            tickets(normal_hour(), self.per_answer)
        )

    @property
    def peak(self) -> Decimal:
        hour = sum(
            (self.per_answer[j] * n for j, n in HOUR.items()),
            Decimal(0),
        )
        return hour / HOUR.total() * PEAK


def run(model: str) -> Run:
    m = measure(model=model)
    per: dict[str, Decimal] = {j: m.spend[j].cost for j in HOUR}
    return Run(model, per, m.texts)


def main() -> None:
    before, after = run(MODEL), run(FALLBACK)
    found = tickets(normal_hour(), before.per_answer)
    done = sum(t.resolved for t in found)
    same = "yes" if before.texts == after.texts else "no"
    print("FS-13: a costly fallback (mock provider: SIMULATED)")
    print(f"  {'':<34}{MODEL:<14}{FALLBACK}")

    def row(label: str, a: object, b: object) -> None:
        print(f"  {label:<34}{a!s:<14}{b}")

    row("answers the same", "-", same)
    row("resolved conversations", f"{done} of {len(found)}",
        f"{done} of {len(found)}")  # fmt: skip
    row(
        "cost per resolved ticket (USD)",
        f"{before.per_resolved:.7f}",
        f"{after.per_resolved:.7f}",
    )
    row("at 40 answers a second (USD/h)", f"{before.peak:.2f}",
        f"{after.peak:.2f}")  # fmt: skip
    row("share of the $60 hourly limit", f"{before.peak / LIMIT:.0%}",
        f"{after.peak / LIMIT:.0%}")  # fmt: skip
    minutes = LIMIT / after.peak * 60
    print(f"  at the peak, the fallback reaches the limit in "
          f"{minutes:.0f} minutes")  # fmt: skip
