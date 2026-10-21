"""Gateway comparison lab: FS-01 and FS-18, two ways (SIMULATED).

uv sync --group lab
uv run python scripts/gateway_lab.py

The official OpenAI instrumentation with SDK retries on, against
the book's gateway, on the same mock provider.
"""

import asyncio
import time
from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass

import openai
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from services.mock_llm.faults import FS01_HIDDEN_RETRY_STORM
from services.mock_llm.server import RunningProvider, running_provider
from wrenholt.gateway import Gateway, Message, ProviderError, Route
from wrenholt.labs.layered import instrument_default
from wrenholt.orchestrator.baseline import answer, make_client
from wrenholt.telemetry import conventions as c

MODEL = "mock-a-fast"
QUESTION = "When will my refund arrive?"


@dataclass(frozen=True)
class Run:
    outcome: str
    provider: tuple[int, ...]  # statuses the mock provider saw
    spans: tuple[ReadableSpan, ...]
    seconds: float


def scenario(name: str) -> AbstractContextManager[RunningProvider]:
    if name == "fs01":
        return running_provider(FS01_HIDDEN_RETRY_STORM)
    if name == "fs18":
        return running_provider(spend_cap=True)
    return running_provider()


def official(exporter: InMemorySpanExporter, name: str) -> Run:
    exporter.clear()
    with scenario(name) as mock:
        client = make_client(mock.base_url, "sk-mock")
        start = time.perf_counter()
        try:
            outcome = answer(client, MODEL, QUESTION)
        except openai.APIStatusError as exc:
            outcome = type(exc).__name__
        seconds = time.perf_counter() - start
        statuses = tuple(r.status for r in mock.log.items())
    spans = tuple(exporter.get_finished_spans())
    return Run(outcome, statuses, spans, seconds)


def gateway(
    exporter: InMemorySpanExporter,
    provider: TracerProvider,
    name: str,
) -> Run:
    exporter.clear()
    with scenario(name) as mock:
        route = Route("wrenholt.mock_a", mock.base_url, "sk-mock")

        async def ask() -> str:
            gw = Gateway({MODEL: route}, tracer_provider=provider)
            try:
                reply = await gw.chat(
                    MODEL, [Message("user", QUESTION)]
                )
                return reply.text
            except ProviderError as err:
                return err.error_type.value
            finally:
                await gw.aclose()

        start = time.perf_counter()
        outcome = asyncio.run(ask())
        seconds = time.perf_counter() - start
        statuses = tuple(r.status for r in mock.log.items())
    spans = tuple(exporter.get_finished_spans())
    return Run(outcome, statuses, spans, seconds)


@contextmanager
def official_off(provider: TracerProvider) -> Iterator[None]:
    """The gateway's own spans only: the official OpenAI
    instrumentation would add GenAI spans inside every attempt."""
    OpenAIInstrumentor().uninstrument()
    try:
        yield
    finally:
        OpenAIInstrumentor().instrument(tracer_provider=provider)


def genai(run: Run) -> ReadableSpan:
    (span,) = [s for s in run.spans if s.name == f"{c.CHAT} {MODEL}"]
    return span


def attempts(run: Run) -> list[ReadableSpan]:
    return [s for s in run.spans if s.name.startswith("attempt ")]


def attr(span: ReadableSpan, key: str) -> str:
    value = (span.attributes or {}).get(key)
    return "-" if value is None else str(value)


def short(outcome: str) -> str:
    return "answered" if outcome.startswith("Refunds") else outcome


def compare(left: Run, right: Run, rows: Sequence[str]) -> list[str]:
    def cell(run: Run, row: str) -> str:
        span = genai(run)
        if row == "outcome":
            return short(run.outcome)
        if row == "provider requests":
            return str(len(run.provider))
        if row == "attempt spans":
            return str(len(attempts(run)))
        if row == "retry-after seen":
            seen = [
                attr(a, c.ATTEMPT_RETRY_AFTER) for a in attempts(run)
            ]
            return ", ".join(s for s in seen if s != "-") or "-"
        if row == "duration s":
            return f"{run.seconds:.2f}"
        return attr(span, row)

    return [
        f"  {r:<22}{cell(left, r):<24}{cell(right, r)}" for r in rows
    ]


def tree(run: Run) -> list[str]:
    by_id = {s.context.span_id: s for s in run.spans if s.context}
    t0 = min(s.start_time or 0 for s in run.spans)

    def depth(span: ReadableSpan) -> int:
        level = 0
        while span.parent and span.parent.span_id in by_id:
            span = by_id[span.parent.span_id]
            level += 1
        return level

    head = f"{'span':<26}{'start ms':>9}{'dur ms':>8}{'http':>6}"
    lines = [f"{head}  error.type"]
    for s in sorted(run.spans, key=lambda x: x.start_time or 0):
        start, end = s.start_time or 0, s.end_time or 0
        name = "  " * depth(s) + s.name
        http = attr(s, c.HTTP_STATUS)
        lines.append(
            f"{name:<26}{(start - t0) / 1e6:>9.1f}"
            f"{(end - start) / 1e6:>8.1f}{http:>6}  "
            f"{attr(s, c.ERROR_TYPE)}"
        )
    return lines


def main() -> None:
    exporter = InMemorySpanExporter()
    provider = instrument_default(exporter)
    official(exporter, "none")  # warm-up, not reported
    runs = {
        name: official(exporter, name) for name in ("fs01", "fs18")
    }
    with official_off(provider):
        gateway(exporter, provider, "none")  # warm-up
        gw = {
            name: gateway(exporter, provider, name) for name in runs
        }
    head = f"  {'':<22}{'official, SDK retries':<24}gateway"
    rows01 = (
        "outcome",
        "provider requests",
        "attempt spans",
        "retry-after seen",
        c.PROVIDER_NAME,
        c.SERVER_ADDRESS,
        "duration s",
    )
    rows18 = (
        "outcome",
        "provider requests",
        c.ERROR_TYPE,
        "duration s",
    )
    print("Gateway comparison lab (mock provider: SIMULATED)")
    print("FS-01: two 429s with retry-after 1 s, then an answer")
    print(
        "\n".join([head, *compare(runs["fs01"], gw["fs01"], rows01)])
    )
    print("FS-18: spend cap exhausted (429, billing code)")
    print("\n".join(compare(runs["fs18"], gw["fs18"], rows18)))
    print()
    print("FS-01 through the gateway")
    print("\n".join(tree(gw["fs01"])))
