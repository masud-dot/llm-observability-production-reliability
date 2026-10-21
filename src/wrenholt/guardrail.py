"""Linnet's input guardrail (Chapter 12; SIMULATED).

A versioned list of patterns, screened before Linnet answers.
Designing real guardrails belongs to *Secure AI Agents & MCP*; this
one exists to show what a rule that blocks too much does to the
objectives (FS-17). Its span records the version and the rule that
blocked, never the words that matched.
"""

import re
from dataclasses import dataclass

from opentelemetry import trace

from wrenholt.telemetry import conventions as c


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: re.Pattern[str]


OVERRIDE = Rule(
    "instruction_override",
    re.compile(r"\bignore (all |any )?(previous|prior) instructions",
               re.IGNORECASE),
)  # fmt: skip
# Version 2 adds a rule meant for scripted refund fraud. It also
# matches every customer who says how much they want back: FS-17.
REFUND_FRAUD = Rule(
    "refund_fraud", re.compile(r"\brefund\b.*£\d", re.IGNORECASE)
)
VERSIONS: dict[str, tuple[Rule, ...]] = {
    "1": (OVERRIDE,),
    "2": (OVERRIDE, REFUND_FRAUD),
}
REFUSAL = (
    "I can't help with that here. A member of the team can: reply "
    "'agent' to reach one."
)


class Guardrail:
    def __init__(
        self,
        version: str = "1",
        tracer_provider: trace.TracerProvider | None = None,
    ) -> None:
        self.version, self._rules = version, VERSIONS[version]
        self._tracer = trace.get_tracer(
            c.GUARDRAIL, tracer_provider=tracer_provider
        )

    def screen(self, text: str) -> str | None:
        """The id of the first rule the text breaks, or None."""
        with self._tracer.start_as_current_span(
            c.GUARDRAIL,
            attributes={c.GUARDRAIL_VERSION: self.version},
        ) as span:
            for rule in self._rules:
                if rule.pattern.search(text):
                    span.set_attribute(c.GUARDRAIL_RULE, rule.id)
                    return rule.id
        return None
