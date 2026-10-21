"""Shared harness for Chapter 9's labs (SIMULATED workloads).

Linnet runs in process with in-memory span and metric exporters,
against the mock provider and the orders service, each on a free
local port.
"""

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from services.mock_llm.server import running_provider
from services.orders.app import create_app as orders_app
from services.orders.faults import Faults
from services.orders.store import OrderStore, generate_orders
from services.serving import serve
from wrenholt.gateway import Gateway, Route
from wrenholt.orchestrator.guard import LoopGuard
from wrenholt.orchestrator.linnet import Answer, Linnet
from wrenholt.rag.corpus import TODAY
from wrenholt.rag.embed import EMBEDDERS, Embedder
from wrenholt.rag.index import Index, index_as_of
from wrenholt.rag.retriever import Retriever
from wrenholt.tools.orders import OrdersClient
from wrenholt.tools.toolbox import Toolbox

MODEL = "mock-a-fast"
EMBED_1 = EMBEDDERS["wrenholt-embed-1"]


@dataclass
class Telemetry:
    spans: InMemorySpanExporter = field(
        default_factory=InMemorySpanExporter
    )
    reader: InMemoryMetricReader = field(
        default_factory=InMemoryMetricReader
    )

    def __post_init__(self) -> None:
        self.tracing = TracerProvider()
        self.tracing.add_span_processor(
            SimpleSpanProcessor(self.spans)
        )
        self.meters = MeterProvider(metric_readers=[self.reader])

    def named(self, prefix: str) -> list[ReadableSpan]:
        return [
            s
            for s in self.spans.get_finished_spans()
            if s.name.startswith(prefix)
        ]

    def points(self, name: str) -> list[Any]:
        data = self.reader.get_metrics_data()
        return [
            p
            for r in (data.resource_metrics if data else [])
            for s in r.scope_metrics
            for m in s.metrics
            if m.name == name
            for p in m.data.data_points
        ]


@dataclass
class Setup:
    """What one lab run varies."""

    guard: Callable[[], LoopGuard] = LoopGuard
    toolbox: type[Toolbox] = Toolbox
    index: Index | None = None
    embedder: Embedder = EMBED_1
    retriever: type[Retriever] = Retriever
    tool_loop: bool = False
    faults: Faults = field(default_factory=Faults)
    timeout_s: float = 2.0


@contextmanager
def services(
    setup: Setup, store: OrderStore
) -> Iterator[tuple[str, str]]:
    """The mock provider and the orders service, running."""
    app = orders_app(store, setup.faults)
    with (
        running_provider(tool_loop=setup.tool_loop) as mock,
        serve(app) as orders_url,
    ):
        yield mock.base_url, orders_url


def ask(
    questions: list[str],
    setup: Setup,
    t: Telemetry,
    store: OrderStore | None = None,
) -> list[Answer]:
    """Linnet answers each question in turn, whole."""
    store = (
        store if store is not None else OrderStore(generate_orders())
    )
    index = setup.index or index_as_of(TODAY, setup.embedder)
    retriever = setup.retriever(
        index,
        setup.embedder,
        tracer_provider=t.tracing,
        meter_provider=t.meters,
    )
    linnet = Linnet(
        retriever,
        guard=setup.guard,
        toolbox=setup.toolbox,
        tracer_provider=t.tracing,
        meter_provider=t.meters,
    )
    with services(setup, store) as (provider, orders_url):

        async def go() -> list[Answer]:
            route = Route("wrenholt.mock_a", provider, "sk-mock")
            gw = Gateway(
                {MODEL: route},
                tracer_provider=t.tracing,
                meter_provider=t.meters,
            )
            orders = OrdersClient(orders_url, timeout=setup.timeout_s)
            try:
                return [
                    await linnet.answer(gw, MODEL, q, orders)
                    for q in questions
                ]
            finally:
                await orders.aclose()
                await gw.aclose()

        return asyncio.run(go())
