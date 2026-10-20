"""Gates lab (Chapter 20): FS-10 in CI, FS-11 in the canary
(SIMULATED).

    uv run --group lab python scripts/gates.py lab

FS-10's prompt meets the evaluation gate in CI. FS-11's model
change passes CI, which never calls the provider, and meets the
canary: one answer in ten goes to the new release, which reaches
the provider's new endpoint, and the two releases are compared by
service.version.
"""

import asyncio
from decimal import Decimal

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from services.mock_llm.model_swap import FS11_SWAP
from services.mock_llm.server import running_provider
from wrenholt.api.app import PINNED
from wrenholt.gates import (
    Spend,
    Verdict,
    budget,
    budget_gate,
    canary,
    evaluation,
    gates,
    kinds,
    populations,
    verdict,
)
from wrenholt.gateway import Gateway, Message, RetryPolicy, Route
from wrenholt.gateway.context import prompt
from wrenholt.labs.eval_lab import run
from wrenholt.labs.fs10_lab import V3
from wrenholt.labs.fs11_lab import MODEL, QUESTION
from wrenholt.labs.fs12_lab import HOUR
from wrenholt.orchestrator.prompts import SUPPORT, Prompt
from wrenholt.telemetry import conventions as c

PROMPTS = "src/wrenholt/orchestrator/prompts.py"
CONTROL, CANARY = "2026.10.1", "2026.10.2"
ANSWERS = 300  # one in ten to the canary: 270 and 30
SPENDS = (  # scenario inputs, not measurements
    Spend("availability", "platform", Decimal("-0.2"), outside=True),
    Spend("not_refused", "assistant", Decimal("-0.05")),
)
CHANGES: tuple[tuple[str, set[str]], ...] = (
    ("assistant", set()),
    ("assistant", {"fix"}),
    ("platform", set()),
)


def suite(p: Prompt) -> Verdict:
    """The evaluation gate on one prompt version."""
    seen = run(p)
    mix: dict[str, int] = {j: n for j, n in HOUR.items()}
    refused = {j: seen[j].labels["refusal"] == "refusal" for j in mix}
    return evaluation(refused, mix, budget("not_refused"))


def evaluate() -> int:
    """CI's evaluation gate, on the prompt in the checked-out tree."""
    v = suite(SUPPORT)
    state = "passed" if v.passed else "BLOCKED"
    print(f"evaluation, {SUPPORT.name} {SUPPORT.version}: {state}")
    print(f"  {v.reason}")
    return 0 if v.passed else 1


async def _answers(old: str, moved: str) -> list[ReadableSpan]:
    spans = InMemorySpanExporter()
    releases = {}
    for version, url in ((CONTROL, old), (CANARY, moved)):
        resource = Resource({c.SERVICE_VERSION: version})
        tracing = TracerProvider(resource=resource)
        tracing.add_span_processor(SimpleSpanProcessor(spans))
        releases[version] = Gateway(
            {MODEL: Route("wrenholt.mock_a", url, "sk-mock")},
            RetryPolicy(),
            tracer_provider=tracing,
            meter_provider=MeterProvider(),
            pinned=PINNED,
        )
    messages = [
        Message("system", SUPPORT.text),
        Message("user", QUESTION),
    ]
    for i in range(ANSWERS):
        gw = releases[CANARY if i % 10 == 9 else CONTROL]
        with prompt(SUPPORT.name, SUPPORT.version):
            await gw.chat(MODEL, messages)
    for gw in releases.values():
        await gw.aclose()
    return list(spans.get_finished_spans())


def traffic() -> dict[str, list[ReadableSpan]]:
    """Answers from both releases, split by service.version. The
    canary's new endpoint answers the alias with a newer model."""
    with (
        running_provider() as old,
        running_provider(model_swap=FS11_SWAP) as moved,
    ):
        spans = asyncio.run(_answers(old.base_url, moved.base_url))
    return populations(spans, f"chat {MODEL}")


def main() -> None:
    print("FS-10 in CI (mock provider: SIMULATED)")
    types = ", ".join(sorted(kinds([PROMPTS])))
    print(f"  prompts.py is {types}: {', '.join(gates([PROMPTS]))}")
    for p in (SUPPORT, V3):
        v = suite(p)
        state = "passed" if v.passed else "BLOCKED"
        print(f"  version {p.version}: {state}")
        print(f"    {v.reason}")
    print("FS-11 in the canary (mock provider: SIMULATED)")
    split = traffic()
    print(f"  {'signal':<16}{CONTROL:<12}{CANARY:<12}decision")
    calls = canary(split[CONTROL], split[CANARY])
    for call in calls:
        was = f"{call.control.hits} of {call.control.n}"
        now = f"{call.canary.hits} of {call.canary.n}"
        print(f"  {call.signal:<16}{was:<12}{now:<12}{call.decision}")
    alone = verdict(calls[:1])
    print(f"  errors alone: {alone}; with the pin: {verdict(calls)}")
    print("Error budget policy (scenario)")
    for team, labels in CHANGES:
        print(f"  {budget_gate(SPENDS, team, labels).reason}")
