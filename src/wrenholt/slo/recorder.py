"""The SLIs the API judges (Chapter 12).

Some SLIs can only be judged where a request is handled: whether
the customer got an answer, whether the guardrail refused it, what
the answer cost, whether the passages behind it were the versions
in force. The API judges each event once and counts it good or bad;
the cost threshold comes from the SLO file. The customer's time to
first chunk is a histogram instead, so that its thresholds stay in
the queries the SLO file generates.
"""

import re
import time
from collections.abc import AsyncGenerator, Callable, Mapping
from decimal import Decimal
from typing import Any

from opentelemetry import metrics

from wrenholt.evaluation.context import PASSAGES
from wrenholt.gateway import (
    SPEND,
    Completion,
    Gateway,
    LimitExceeded,
    ProviderError,
    StreamResult,
)
from wrenholt.guardrail import REFUSAL, Guardrail
from wrenholt.orchestrator.linnet import Answer, Linnet
from wrenholt.rag.embed import Embedder
from wrenholt.rag.index import Index
from wrenholt.rag.retriever import Found, Retriever
from wrenholt.slo.objectives import load_objectives
from wrenholt.telemetry import conventions as c
from wrenholt.tools.orders import ORDER_ID, OrdersClient

REFUND = re.compile(r"\brefund", re.IGNORECASE)
# What a refused answer stands on: no model was asked.
REFUSED = Completion(REFUSAL, 0, "", "", ("refused",), None, None)


def request_class(question: str) -> str:
    """Decided from the request, before any work is done: a refund
    asked for on a named order is a critical action."""
    if REFUND.search(question) and ORDER_ID.search(question):
        return "critical_action"
    return "interactive"


class SliRecorder:
    def __init__(
        self,
        meter_provider: metrics.MeterProvider | None = None,
        max_cost: Decimal | None = None,
    ) -> None:
        meter = metrics.get_meter(
            "wrenholt.slo", meter_provider=meter_provider
        )
        self._events = meter.create_counter(
            c.SLO_EVENTS,
            unit="{event}",
            description="SLI events the API judged, good or bad.",
        )
        self._first = meter.create_histogram(
            c.ANSWER_FIRST_CHUNK,
            unit="s",
            description="From the request to the customer's first "
            "chunk.",
            explicit_bucket_boundaries_advisory=c.ANSWER_BUCKETS,
        )
        found = load_objectives().get("answer_cost").max_cost_usd
        cost = max_cost if max_cost is not None else found
        if cost is None:
            raise ValueError("the SLO file sets no cost threshold")
        self.max_cost: Decimal = cost

    def start(self) -> None:
        """Every series at zero, so that the first bad event is an
        increase Prometheus can see, not a series' first value."""
        for sli in c.EVENT_SLIS:
            for good in (True, False):
                attrs = {c.SLO_SLI: sli, c.SLO_GOOD: good}
                self._events.add(0, attrs)

    def event(self, sli: str, good: bool) -> None:
        if sli not in c.EVENT_SLIS:
            raise ValueError(f"the API judges no SLI called {sli}")
        self._events.add(1, {c.SLO_SLI: sli, c.SLO_GOOD: good})

    def first_chunk(self, request_class: str, seconds: float) -> None:
        attrs = {c.REQUEST_CLASS: request_class}
        self._first.record(seconds, attrs)

    def completed(self) -> None:
        """An answer reached the customer: it was available, and it
        cost what its bill says."""
        self.event("availability", True)
        bill = SPEND.get()
        cost = bill.cost if bill is not None else Decimal(0)
        self.event("answer_cost", cost <= self.max_cost)

    def outcome(self, escalated: bool) -> None:
        self.event("resolution", not escalated)


class Screened:
    """Linnet's two entry points as the handlers call them, with the
    guardrail in front and the SLI events recorded around them."""

    def __init__(
        self,
        linnet: Linnet,
        guardrail: Guardrail,
        slis: SliRecorder,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._linnet, self._guardrail = linnet, guardrail
        self._slis, self._clock = slis, clock

    def _refused(self, question: str) -> bool:
        rule = self._guardrail.screen(question)
        self._slis.event("not_refused", rule is None)
        return rule is not None

    async def answer(
        self,
        gateway: Gateway,
        model: str,
        question: str,
        orders: OrdersClient | None = None,
    ) -> Answer:
        start, cls = self._clock(), request_class(question)
        if self._refused(question):
            result = Answer(REFUSAL, REFUSED)
        else:
            try:
                result = await self._linnet.answer(
                    gateway, model, question, orders
                )
            except (ProviderError, LimitExceeded):
                self._slis.event("availability", False)
                raise
        self._slis.first_chunk(cls, self._clock() - start)
        self._slis.completed()
        return result

    async def stream_answer(
        self,
        gateway: Gateway,
        model: str,
        question: str,
        orders: OrdersClient | None,
        result: StreamResult,
    ) -> AsyncGenerator[str]:
        start, cls = self._clock(), request_class(question)
        if self._refused(question):
            self._slis.first_chunk(cls, self._clock() - start)
            yield REFUSAL
            self._slis.completed()
            return
        chunks = self._linnet.stream_answer(
            gateway, model, question, orders, result
        )
        first = True
        try:
            async for piece in chunks:
                if first:
                    self._slis.first_chunk(cls, self._clock() - start)
                    first = False
                yield piece
        except (ProviderError, LimitExceeded):
            # HTTP 503 or 429 before the first chunk, in band after
            self._slis.event("availability", False)
            raise
        finally:
            await chunks.aclose()
        self._slis.completed()  # not reached if the customer left


class CheckedRetriever(Retriever):
    """Judges policy_freshness for each search that finds passages:
    good when every one is the version the help centre has in
    force."""

    def __init__(
        self,
        index: Index,
        embedder: Embedder,
        in_force: Mapping[str, str],
        slis: SliRecorder,
        **kwargs: Any,
    ) -> None:
        super().__init__(index, embedder, **kwargs)
        self._in_force, self._slis = in_force, slis

    def search(self, query: str) -> list[Found]:
        found = super().search(query)
        PASSAGES.set(tuple(f.text for f in found))  # Chapter 13
        if found:
            fresh = all(
                self._in_force.get(f.id) == f.version for f in found
            )
            self._slis.event("policy_freshness", fresh)
        return found
