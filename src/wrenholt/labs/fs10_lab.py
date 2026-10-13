"""FS-10 lab (Chapter 13): a prompt regression (SIMULATED).

    uv run python scripts/fs10_prompt_regression.py

Prompt version 3 tells the model to decline anything it cannot
verify, and the model declines to say where an order is. Nothing in
Wrenholt's code refused: the guardrail passed every question and
every request succeeded. Only the refusal evaluation, sliced by
prompt version, sees it, and only as fast as the sample fills.
"""

from dataclasses import dataclass

from services.mock_llm.app import CAUTIOUS
from wrenholt.evaluation.drift import Rate, Shift, rate_shift
from wrenholt.labs.eval_lab import RATE, WEEK, Seen, hours_to, run
from wrenholt.labs.fs12_lab import HOUR
from wrenholt.orchestrator.prompts import SUPPORT, Prompt

V3 = Prompt(SUPPORT.name, "3", f"{SUPPORT.text} {CAUTIOUS}")
SENSOR = "refusal/1"


@dataclass(frozen=True)
class Report:
    before: dict[str, Seen]
    after: dict[str, Seen]

    def refusals(self, seen: dict[str, Seen]) -> int:
        """Refusals in an hour of FS-09's normal mix."""
        return sum(
            n
            for j, n in HOUR.items()
            if seen[j].labels["refusal"] == "refusal"
        )

    def flagged(self, share: float) -> tuple[int, Shift | None]:
        """Hours, and the verdict, once version 3 serves `share` of
        answers and a tenth of them are evaluated."""
        per_hour = HOUR.total() * share * RATE
        hours = hours_to(per_hour)
        refused = self.refusals(self.after) / HOUR.total()
        base = Rate(0, int(HOUR.total() * RATE * WEEK), SENSOR)
        n = int(per_hour * hours)
        now = Rate(int(n * refused), n, SENSOR)
        return hours, rate_shift(base, now)


def run_lab() -> Report:
    return Report(run(SUPPORT), run(V3))


def main() -> None:
    r = run_lab()
    print("FS-10: a prompt regression (mock provider: SIMULATED)")
    for journey in HOUR:
        was = r.before[journey].labels["refusal"]
        now = r.after[journey]
        label, said = now.labels["refusal"], now.text[:31].rstrip()
        print(f"  {journey:<17}{was:<9}{label:<9}{said}")
    v1, v3 = r.refusals(r.before), r.refusals(r.after)
    print(f"  refusals in an hour: version 1 {v1}, "
          f"version 3 {v3} of {HOUR.total()}")  # fmt: skip
    rollouts = ((1.0, "full rollout"), (0.1, "10% canary"))
    for share, rollout in rollouts:
        hours, shift = r.flagged(share)
        z = "-" if shift is None else f"{shift.statistic:.1f}"
        print(f"  {rollout}, 10% evaluated: flagged after "
              f"{hours} hours (z = {z})")  # fmt: skip
