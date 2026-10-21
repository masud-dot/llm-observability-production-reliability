"""FS-09 again (Chapter 13): two index builds (SIMULATED).

    uv run python scripts/fs09_index_swap.py

During an index swap half of the policy questions reach a build made
before the returns window fell from 60 to 30 days. Evaluated, their
answers are grounded in what they retrieved, and wrong. Sliced by
index version, the policy-accuracy results say which build.
"""

from dataclasses import dataclass

from wrenholt.labs.eval_lab import RATE, Seen, hours_to, run
from wrenholt.labs.fs12_lab import HOUR
from wrenholt.rag.corpus import TODAY

STALE = "2026-02-01"  # a build from before the change
POLICY = {"policy_question": "How long do I have to return an item?"}


@dataclass(frozen=True)
class Report:
    stale: Seen
    current: Seen

    @property
    def hours(self) -> int:
        """Until each build's slice holds 30 results, half the
        policy questions each, a tenth of them evaluated."""
        return hours_to(HOUR["policy_question"] / 2 * RATE)


def run_lab() -> Report:
    stale = run(as_of=STALE, questions=POLICY)["policy_question"]
    current = run(as_of=TODAY, questions=POLICY)["policy_question"]
    return Report(stale, current)


def main() -> None:
    r = run_lab()
    print("FS-09 during an index swap (mock provider: SIMULATED)")
    builds = (("old build", r.stale), ("new build", r.current))
    for name, seen in builds:
        grounded = seen.labels["groundedness"]
        accurate = seen.labels["policy_accuracy"]
        print(f"  {name}: {seen.text}")
        print(f"    groundedness {grounded}, accuracy {accurate}")
    print(f"  each build's slice holds 30 results after {r.hours} h")
