"""FS-06 lab (Chapter 9): a tool-call loop (SIMULATED).

    uv run python scripts/fs06_tool_loop.py

The mock model asks for the same order lookup at every step. Linnet
answers one order question twice: first with only a generous step
cap, as many agent loops run, then with the chapter's guard.
"""

import textwrap
from dataclasses import dataclass

from wrenholt.gateway import ToolCall
from wrenholt.labs.agent_lab import Setup, Telemetry, ask
from wrenholt.orchestrator.guard import LoopGuard
from wrenholt.telemetry import conventions as c

QUESTION = "Where is order WG-100006?"


class CapOnly(LoopGuard):
    """Before the guard: 25 steps and no repetition check."""

    def __init__(self) -> None:
        super().__init__(max_steps=25)

    def repeats(self, call: ToolCall) -> bool:
        return False


@dataclass(frozen=True)
class Outcome:
    stop: str
    model_calls: int
    tool_calls: int
    fingerprints: int  # distinct argument fingerprints
    bucket: str  # the tool_calls bucket the invocation fell in
    seconds: float
    answer: str


def bucket(t: Telemetry) -> str:
    (point,) = t.points(c.AGENT_TOOL_CALLS)
    for bound, count in zip(
        point.explicit_bounds, point.bucket_counts, strict=False
    ):
        if count:
            return f'le="{bound:g}"'
    return 'le="+Inf"'


def run(guard: type[LoopGuard]) -> Outcome:
    t = Telemetry()
    (answer,) = ask([QUESTION], Setup(guard=guard, tool_loop=True), t)
    (span,) = t.named(c.INVOKE_AGENT)
    seconds = ((span.end_time or 0) - (span.start_time or 0)) / 1e9
    agent = span.attributes or {}
    tools = [s.attributes or {} for s in t.named(c.EXECUTE_TOOL)]
    (calls,) = t.points(c.AGENT_INFERENCE_CALLS)
    prints = {str(a[c.TOOL_FINGERPRINT]) for a in tools}
    return Outcome(
        str(agent[c.AGENT_STOP]),
        int(calls.sum),
        len(tools),
        len(prints),
        bucket(t),
        seconds,
        answer.text,
    )


def main() -> None:
    before, after = run(CapOnly), run(LoopGuard)
    rows = [
        ("loop limit", "25-step cap", "repeat check, 5 steps"),
        ("stop reason", before.stop, after.stop),
        ("model calls", before.model_calls, after.model_calls),
        ("tool calls", before.tool_calls, after.tool_calls),
        ("argument fingerprints", before.fingerprints,
         after.fingerprints),
        ("tool_calls bucket", before.bucket, after.bucket),
        ("invoke_agent span", f"{before.seconds:.2f} s",
         f"{after.seconds:.2f} s"),
    ]  # fmt: skip
    print("FS-06: a tool-call loop (mock provider: SIMULATED)")
    print(f'"{QUESTION}"; the model repeats its lookup')
    print(f"{'':<23}{'before':<15}after")
    for label, a, b in rows:
        print(f"{label:<23}{a!s:<15}{b}")
    same = before.answer == after.answer
    print(f"answer, {'both runs' if same else 'differs'}:")
    print(textwrap.fill(after.answer, 68, initial_indent="  ",
                        subsequent_indent="  "))  # fmt: skip
