"""FS-11 lab (Chapter 6): a silent model change (SIMULATED).

    uv run python scripts/fs11_model_change.py

One question goes through the gateway twice, against the same mock
provider: before and after it starts answering mock-a-fast with a
newer model version. Nothing fails; the pin and the bundle notice.
"""

import asyncio
import json
from dataclasses import dataclass

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from services.mock_llm.model_swap import FS11_SWAP
from services.mock_llm.server import running_provider
from wrenholt.api.app import PINNED
from wrenholt.gateway import Gateway, Message, RetryPolicy, Route
from wrenholt.gateway.context import prompt
from wrenholt.orchestrator.prompts import SUPPORT
from wrenholt.repro import Bundle, bundle
from wrenholt.telemetry import conventions as c

MODEL = "mock-a-fast"
QUESTION = "When will my refund arrive?"


@dataclass(frozen=True)
class Outcome:
    text: str
    response_model: str
    mismatch: bool
    mismatches: int
    bundle: Bundle


def ask(route: Route) -> Outcome:
    spans = InMemorySpanExporter()
    tracing = TracerProvider()
    tracing.add_span_processor(SimpleSpanProcessor(spans))
    reader = InMemoryMetricReader()
    policy = RetryPolicy()

    async def go() -> tuple[str, str]:
        gw = Gateway(
            {MODEL: route},
            policy,
            tracer_provider=tracing,
            meter_provider=MeterProvider(metric_readers=[reader]),
            pinned=PINNED,
        )
        messages = [
            Message("system", SUPPORT.text),
            Message("user", QUESTION),
        ]
        with prompt(SUPPORT.name, SUPPORT.version):
            done = await gw.chat(MODEL, messages)
        await gw.aclose()
        return done.text, done.response_model

    text, model = asyncio.run(go())
    (request,) = [
        s
        for s in spans.get_finished_spans()
        if s.name == f"chat {MODEL}"
    ]
    flag = bool((request.attributes or {}).get(c.MODEL_MISMATCH))
    count = 0
    data = reader.get_metrics_data()
    for resource in data.resource_metrics if data else []:
        for scope in resource.scope_metrics:
            for m in scope.metrics:
                if m.name == c.MODEL_MISMATCHES:
                    points = list(m.data.data_points)
                    count += sum(
                        int(getattr(p, "value", 0)) for p in points
                    )
    context = request.get_span_context()
    assert context is not None
    item = bundle(
        context,
        SUPPORT,
        model,
        route,
        MODEL,
        PINNED[MODEL],
        policy,
    )
    return Outcome(text, model, flag, count, item)


def run() -> tuple[Outcome, Outcome]:
    """Before and after the swap, against one provider."""
    swaps: dict[str, str] = {}
    with running_provider(model_swap=swaps) as mock:
        route = Route("wrenholt.mock_a", mock.base_url, "sk-mock")
        before = ask(route)
        swaps.update(FS11_SWAP)  # the provider moves the alias
        after = ask(route)
    return before, after


def differences(a: Bundle, b: Bundle) -> list[str]:
    left, right = json.loads(a.to_json()), json.loads(b.to_json())
    moving = {"trace_id", "recorded_at"}  # differ on every request
    return sorted(
        k for k in left if left[k] != right[k] and k not in moving
    )


def main() -> None:
    before, after = run()
    same = "same" if after.text == before.text else "changed"
    rows = [
        (
            "response model",
            before.response_model,
            after.response_model,
        ),
        ("pinned model", PINNED[MODEL], PINNED[MODEL]),
        ("model_mismatch", str(before.mismatch), str(after.mismatch)),
        (
            "mismatch counter",
            str(before.mismatches),
            str(after.mismatches),
        ),
        ("answer text", "-", same),
    ]
    print("FS-11: a silent model change (mock provider: SIMULATED)")
    print(f"  {'':<18}{'before':<22}after")
    for label, left, right in rows:
        print(f"  {label:<18}{left:<22}{right}")
    changed = ", ".join(differences(before.bundle, after.bundle))
    print(f"bundle fields that differ: {changed}")
