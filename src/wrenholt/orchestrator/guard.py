"""The loop guard (Chapter 9).

An agent loop ends when the model says it is done. The guard ends
it sooner in two cases: the model asks for a call it has already
made, arguments and all, which is the step repetition MAST lists
among multi-agent failure modes; or the loop runs out of steps.
One guard serves one invocation.
"""

from dataclasses import dataclass, field

from wrenholt.gateway import ToolCall
from wrenholt.tools.toolbox import canonical

FINISHED = "finished"  # the model called finish
REPEATED = "repeated_call"  # the guard stopped a repeat
STEP_LIMIT = "step_limit"  # the guard ran out of steps
NO_TOOLS = "no_tools"  # nothing to look up: no loop ran


@dataclass
class LoopGuard:
    max_steps: int = 5
    steps: int = 0
    seen: set[str] = field(default_factory=set)

    def step(self) -> bool:
        """Count a decision step; False once the limit is spent."""
        self.steps += 1
        return self.steps <= self.max_steps

    def repeats(self, call: ToolCall) -> bool:
        """True if this exact call already ran in this invocation.
        Call IDs differ between repeats, so they are ignored."""
        key = f"{call.name}:{canonical(call.arguments)}"
        if key in self.seen:
            return True
        self.seen.add(key)
        return False
