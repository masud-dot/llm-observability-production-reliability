"""Shared harness for Chapter 12's labs (SIMULATED workloads).

Linnet answers one question of each journey with the guardrail and
the SLI recorder in front, wired as the API wires them, against the
mock provider and the orders service. A first answer warms the
provider's prompt cache and is left out, as in Chapter 11. Each
journey's events then count as often as the journey occurs in
FS-09's normal hour: 60 policy questions, 30 order questions and 30
refunds. The help desk reports the hour's six escalations, and
every customer whose answer handed them to a person.
"""

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from services.mock_llm.server import running_provider
from services.orders.app import create_app as orders_app
from services.orders.store import OrderStore, generate_orders
from services.serving import serve
from wrenholt.gateway import SPEND, Gateway, Route, Spend, load_prices
from wrenholt.guardrail import Guardrail
from wrenholt.labs.agent_lab import EMBED_1, Telemetry
from wrenholt.labs.cost_lab import CAP, MODEL, QUESTIONS
from wrenholt.labs.fs12_lab import HOUR
from wrenholt.orchestrator.linnet import Linnet
from wrenholt.rag.corpus import TODAY, snapshot
from wrenholt.rag.index import index_as_of
from wrenholt.slo import errorbudget
from wrenholt.slo.fs09 import normal_hour
from wrenholt.slo.objectives import load_objectives
from wrenholt.slo.recorder import (
    CheckedRetriever,
    Screened,
    SliRecorder,
)
from wrenholt.telemetry import conventions as c
from wrenholt.tools.orders import OrdersClient

HANDED_OFF = "A member of the team"  # what both hand-offs say
ESCALATED = Counter(e.journey for e in normal_hour() if e.escalated)
SLOS = load_objectives()


@dataclass
class Hour:
    good: Counter[str] = field(default_factory=Counter)
    valid: Counter[str] = field(default_factory=Counter)
    texts: dict[str, str] = field(default_factory=dict)
    cost: dict[str, Decimal] = field(default_factory=dict)

    def bad(self, slo: str) -> int:
        return self.valid[slo] - self.good[slo]

    def share(self, slo: str) -> str:
        return f"{self.good[slo]} of {self.valid[slo]}"

    def burn(self, slo: str) -> Decimal | None:
        """None when the SLI saw no events, or has no objective."""
        objective = SLOS.get(slo).objective
        if not self.valid[slo] or objective is None:
            return None
        return errorbudget.burn_rate(
            self.bad(slo), self.valid[slo], objective
        )

    @property
    def per_resolved(self) -> Decimal:
        spend = sum(
            (self.cost[j] * n for j, n in HOUR.items()), Decimal(0)
        )
        return spend / self.good["resolution"]


def counted(t: Telemetry) -> tuple[Counter[str], Counter[str]]:
    """Good and valid events per SLO in one answer's telemetry."""
    good: Counter[str] = Counter()
    valid: Counter[str] = Counter()
    for p in t.points(c.SLO_EVENTS):
        sli = p.attributes[c.SLO_SLI]
        valid[sli] += p.value
        good[sli] += p.value if p.attributes[c.SLO_GOOD] else 0
    for s in SLOS.objectives:
        if s.counted_by != "first_chunk":
            continue
        for p in t.points(c.ANSWER_FIRST_CHUNK):
            if p.attributes[c.REQUEST_CLASS] == s.request_class:
                valid[s.slo] += p.count
                good[s.slo] += sum(
                    n
                    for n, bound in zip(
                        p.bucket_counts,
                        p.explicit_bounds,
                        strict=False,
                    )
                    if bound <= (s.threshold_s or 0)
                )
    for p in t.points(c.TOOL_DURATION):
        if p.attributes[c.TOOL_NAME] == "issue_refund":
            valid["decision_validity"] += p.count
            bad = (
                p.attributes.get(c.ERROR_TYPE) == "invalid_arguments"
            )
            good["decision_validity"] += 0 if bad else p.count
    return good, valid


def run(guardrail: str = "1", malformed: bool = False) -> Hour:
    hour = Hour()
    index = index_as_of(TODAY, EMBED_1)
    in_force = {a.id: a.version for a in snapshot()}

    async def one(
        route: Route,
        orders: OrdersClient,
        question: str,
        t: Telemetry,
    ) -> tuple[str, Decimal]:
        slis = SliRecorder(meter_provider=t.meters)
        slis.start()
        gw = Gateway(
            {MODEL: route},
            tracer_provider=t.tracing,
            meter_provider=t.meters,
            prices=load_prices(),
            max_tokens={MODEL: CAP},
        )
        retriever = CheckedRetriever(
            index,
            EMBED_1,
            in_force,
            slis,
            tracer_provider=t.tracing,
            meter_provider=t.meters,
        )
        linnet = Linnet(
            retriever,
            tracer_provider=t.tracing,
            meter_provider=t.meters,
        )
        screened = Screened(
            linnet, Guardrail(guardrail, t.tracing), slis
        )
        bill = Spend("wrenholt")
        SPEND.set(bill)
        try:
            done = await screened.answer(gw, MODEL, question, orders)
        finally:
            await gw.aclose()
        return done.text, bill.cost

    async def go(provider: str, orders_url: str) -> None:
        route = Route("wrenholt.mock_a", provider, "sk-mock")
        orders = OrdersClient(orders_url)
        try:
            warm = QUESTIONS["policy_question"]
            await one(route, orders, warm, Telemetry())
            for journey, n in HOUR.items():
                t = Telemetry()
                asked = QUESTIONS[journey]
                text, cost = await one(route, orders, asked, t)
                good, valid = counted(t)
                for slo in valid:
                    hour.valid[slo] += n * valid[slo]
                    hour.good[slo] += n * good[slo]
                hour.texts[journey], hour.cost[journey] = text, cost
                # what the help desk reports to /outcome
                hour.valid["resolution"] += n
                if HANDED_OFF not in text:
                    resolved = n - ESCALATED[journey]
                    hour.good["resolution"] += resolved
        finally:
            await orders.aclose()

    store = OrderStore(generate_orders())
    with (
        running_provider(malformed_refunds=malformed) as mock,
        serve(orders_app(store)) as orders_url,
    ):
        asyncio.run(go(mock.base_url, orders_url))
    return hour


def report(title: str, label: str, before: Hour, after: Hour) -> None:
    print(f"{title} (mock provider: SIMULATED)")
    print(f"  {'SLO':<22}{'normal':<13}{label:<13}burn rate")
    for s in SLOS.objectives:
        if s.counted_by in ("evaluation", "attempts"):
            continue  # Chapter 13; and no attempt failed
        burn = after.burn(s.slo)
        shown = "-" if burn is None else f"{burn:.0f}"
        was, now = before.share(s.slo), after.share(s.slo)
        print(f"  {s.slo:<22}{was:<13}{now:<13}{shown}")
