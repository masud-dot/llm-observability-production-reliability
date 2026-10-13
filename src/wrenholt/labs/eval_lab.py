"""Shared harness for Chapter 13's labs (SIMULATED workloads).

Linnet answers each question once, wired as the API wires it, with
the guardrail, the SLI recorder and evaluation in front, inside a
request span, and with every answer evaluated. The labs then count
the results as an hour's mix of questions would produce them, and
as a 10 per cent evaluation sample would see them.
"""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from math import ceil

from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)

from services.mock_llm.server import running_provider
from services.orders.app import create_app as orders_app
from services.orders.store import OrderStore, generate_orders
from services.serving import serve
from wrenholt.evaluation.emitter import ResultEmitter
from wrenholt.evaluation.evaluators import standard
from wrenholt.evaluation.online import Evaluating
from wrenholt.gateway import SPEND, Gateway, Route, Spend
from wrenholt.guardrail import Guardrail
from wrenholt.labs.agent_lab import EMBED_1, Telemetry
from wrenholt.labs.cost_lab import MODEL, QUESTIONS, deployed
from wrenholt.orchestrator import linnet
from wrenholt.orchestrator.prompts import SUPPORT, Prompt
from wrenholt.rag.corpus import TODAY, snapshot
from wrenholt.rag.index import index_as_of
from wrenholt.slo.recorder import (
    CheckedRetriever,
    Screened,
    SliRecorder,
)
from wrenholt.telemetry import conventions as c
from wrenholt.tools.orders import OrdersClient

SALE = "Is the sale discount applied to my basket?"
RATE = 0.1  # Settings().evaluation_rate
MIN_RESULTS = 30  # the SLI catalogue's minimum
WEEK = 168  # hours of baseline


@dataclass(frozen=True)
class Seen:
    text: str
    labels: dict[str, str]  # evaluation name: label
    events: int
    linked: bool  # every event under the answer's request span


def hours_to(n_per_hour: float, minimum: int = MIN_RESULTS) -> int:
    """Whole hours until a slice holds enough results."""
    return ceil(minimum / n_per_hour)


def run(
    prompt: Prompt = SUPPORT,
    as_of: str = TODAY,
    questions: Mapping[str, str] = QUESTIONS,
) -> dict[str, Seen]:
    t = Telemetry()
    logs = InMemoryLogRecordExporter()  # type: ignore[no-untyped-call]
    logging = LoggerProvider()
    logging.add_log_record_processor(SimpleLogRecordProcessor(logs))
    tracer = t.tracing.get_tracer("wrenholt.labs")
    slis = SliRecorder(meter_provider=t.meters)
    index = index_as_of(as_of, EMBED_1)
    in_force = {a.id: a.version for a in snapshot()}
    retriever = CheckedRetriever(
        index,
        EMBED_1,
        in_force,
        slis,
        tracer_provider=t.tracing,
        meter_provider=t.meters,
    )
    agent = linnet.Linnet(
        retriever, tracer_provider=t.tracing, meter_provider=t.meters
    )
    screened = Screened(agent, Guardrail("1", t.tracing), slis)

    def versions() -> tuple[str, str]:
        used: Prompt = vars(linnet)["SUPPORT"]
        return used.version, index.version

    results = ResultEmitter(logging, t.meters)
    evaluating = Evaluating(
        screened, standard(), results, 1.0, versions
    )
    seen: dict[str, Seen] = {}

    async def go(provider: str, orders_url: str) -> None:
        route = Route("wrenholt.mock_a", provider, "sk-mock")
        gw = Gateway(
            {MODEL: route},
            tracer_provider=t.tracing,
            meter_provider=t.meters,
        )
        orders = OrdersClient(orders_url)
        try:
            for name, question in questions.items():
                before = len(logs.get_finished_logs())
                with tracer.start_as_current_span(
                    "POST /chat"
                ) as span:
                    SPEND.set(Spend("wrenholt"))
                    done = await evaluating.answer(
                        gw, MODEL, question, orders
                    )
                request = span.get_span_context()
                records = [
                    r.log_record
                    for r in logs.get_finished_logs()[before:]
                ]
                labels = {
                    str((r.attributes or {})[c.EVALUATION_NAME]): str(
                        (r.attributes or {})[c.EVALUATION_LABEL]
                    )
                    for r in records
                }
                linked = all(
                    (r.trace_id, r.span_id)
                    == (request.trace_id, request.span_id)
                    and r.event_name == c.EVALUATION_RESULT
                    for r in records
                )
                seen[name] = Seen(
                    done.text, labels, len(records), linked
                )
        finally:
            await orders.aclose()
            await gw.aclose()

    store = OrderStore(generate_orders())
    with (
        running_provider() as mock,
        serve(orders_app(store)) as orders_url,
        deployed(prompt),
    ):
        asyncio.run(go(mock.base_url, orders_url))
    return seen
