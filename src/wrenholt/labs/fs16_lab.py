"""FS-16 lab (Chapter 13): sale-day intent drift (SIMULATED).

    uv run python scripts/fs16_intent_drift.py

On a sale day more customers ask where their orders are, and some
ask about the sale itself, which the help centre does not cover. The
intent mix of the evaluated sample moves; the quality evaluations
pass the sale questions by not applying to them.
"""

from collections import Counter
from dataclasses import dataclass

from wrenholt.evaluation.drift import Mix, Shift, mix_shift
from wrenholt.labs.cost_lab import QUESTIONS
from wrenholt.labs.eval_lab import RATE, SALE, WEEK, Seen, run
from wrenholt.labs.fs12_lab import HOUR

SENSOR = "intent/1"
# An hour of the sale (SIMULATED): 160 answers instead of 120.
SALE_HOUR = Counter(
    policy_question=40, order_status=70, refund_request=20, sale=30
)


@dataclass(frozen=True)
class Report:
    seen: dict[str, Seen]

    def mix(self, hour: Counter[str], hours: int) -> Mix:
        """Intent labels of the evaluated tenth of `hours` hours."""
        counts: Counter[str] = Counter()
        for journey, n in hour.items():
            label = self.seen[journey].labels["intent"]
            counts[label] += int(n * RATE * hours)
        return Mix(counts, SENSOR)

    def flagged(self) -> tuple[int, Shift | None]:
        base = self.mix(Counter(HOUR), WEEK)
        hours, shift = 0, None
        while shift is None or not shift.flagged:
            hours += 1
            shift = mix_shift(base, self.mix(SALE_HOUR, hours))
        return hours, shift


def run_lab() -> Report:
    return Report(run(questions={**QUESTIONS, "sale": SALE}))


def main() -> None:
    r = run_lab()
    print("FS-16: sale-day intent drift (mock provider: SIMULATED)")
    sale = r.seen["sale"]
    print(f"  the sale question: {sale.text}")
    print(f"    evaluated: {sale.labels}")
    hours, shift = r.flagged()
    assert shift is not None
    print(f"  intent mix flagged after {hours} hours "
          f"(distance {shift.statistic:.3f})")  # fmt: skip
