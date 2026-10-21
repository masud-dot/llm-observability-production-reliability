"""FS-12 lab (Chapter 11): a token explosion (SIMULATED).

    uv run python scripts/fs12_token_explosion.py

Version 2 of Linnet's prompt asks for thorough answers instead of
brief ones. Each journey is answered under both versions and scaled
to FS-09's normal hour: 60 policy questions, 30 order questions and
30 refunds. Nothing fails. The output-token histogram and the bill
show the change; the cap of 512 tokens a call does not.
"""

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from wrenholt.economics import bucket_counts, histogram_quantile
from wrenholt.labs.cost_lab import CAP, V2, measure
from wrenholt.orchestrator.prompts import SUPPORT, Prompt
from wrenholt.slo.fs09 import normal_hour
from wrenholt.telemetry import conventions as c

HOUR = Counter(e.journey for e in normal_hour())  # 60, 30, 30
PEAK = 40 * 3600  # answers in an hour at the planning figure
# The mock streams one word a chunk: 0.4 s, then 0.12 s a chunk.
FIRST_S, GAP_S = 0.4, 0.12


@dataclass(frozen=True)
class Run:
    version: str
    per_answer: dict[str, Decimal]  # cost, by journey
    outputs: list[int]  # every call of the hour, output tokens
    inputs: list[int]  # and input tokens
    refund_inputs: list[int]  # one refund, call by call
    final_words: int  # the policy answer's

    @property
    def hour(self) -> Decimal:
        return sum(
            (self.per_answer[j] * n for j, n in HOUR.items()),
            Decimal(0),
        )

    @property
    def peak(self) -> Decimal:
        return self.hour / HOUR.total() * PEAK

    def p99(self) -> float:
        bounds = c.TOKEN_BUCKETS
        counts = bucket_counts(self.outputs, bounds)
        return histogram_quantile(0.99, bounds, counts)

    def over(self, tokens: int) -> int:
        return sum(n > tokens for n in self.outputs)


def streamed_s(words: int) -> float:
    """An answer's time at the mock's streaming pace."""
    return FIRST_S + (words - 1) * GAP_S


def run(prompt: Prompt) -> Run:
    m = measure(prompt=prompt)
    outputs: list[int] = []
    inputs: list[int] = []
    for journey, n in HOUR.items():
        for span in m.calls[journey]:
            attrs = span.attributes or {}
            outputs += [int(str(attrs[c.OUTPUT_TOKENS]))] * n
            inputs += [int(str(attrs[c.INPUT_TOKENS]))] * n
    refund = [
        int(str((s.attributes or {})[c.INPUT_TOKENS]))
        for s in m.calls["refund_request"]
    ]
    return Run(
        prompt.version,
        {j: m.spend[j].cost for j in HOUR},
        outputs,
        inputs,
        refund,
        len(m.texts["policy_question"].split()),
    )


def main() -> None:
    before, after = run(SUPPORT), run(V2)
    print("FS-12: a token explosion (mock provider: SIMULATED)")
    print(f"  {'':<34}{'version 1':<14}version 2")
    calls = len(before.outputs)

    def row(label: str, a: object, b: object) -> None:
        print(f"  {label:<34}{a!s:<14}{b}")

    row("model calls in the hour", calls, len(after.outputs))
    row("output tokens, p99 (histogram)", f"{before.p99():.1f}",
        f"{after.p99():.1f}")  # fmt: skip
    row("calls over 64 output tokens", before.over(64),
        after.over(64))  # fmt: skip
    row("calls cut at the cap", before.over(CAP - 1),
        after.over(CAP - 1))  # fmt: skip
    mean_in = [sum(r.inputs) / len(r.inputs) for r in (before, after)]
    row("input tokens per call, mean", f"{mean_in[0]:.1f}",
        f"{mean_in[1]:.1f}")  # fmt: skip
    row("cost of the hour (USD)", before.hour, after.hour)
    row("at 40 answers a second (USD/h)", f"{before.peak:.2f}",
        f"{after.peak:.2f}")  # fmt: skip
    row("policy answer, streamed (s)",
        f"{streamed_s(before.final_words):.2f}",
        f"{streamed_s(after.final_words):.2f}")  # fmt: skip
    growth = ", ".join(str(n) for n in before.refund_inputs)
    print(f"  one refund, input tokens by call: {growth}")
