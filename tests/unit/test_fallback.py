"""Fallbacks, degraded answers and admission (Chapter 17)."""

import asyncio
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import strategies as st

from services.mock_llm.faults import NO_FAULTS, FaultPlan
from services.mock_llm.server import running_provider
from wrenholt.api.admission import Admission
from wrenholt.api.app import Settings, create_app
from wrenholt.gateway import Route, load_prices
from wrenholt.gateway.deadlines import deadline
from wrenholt.gateway.errors import ProviderError
from wrenholt.gateway.fallback import (
    FallbackGateway,
    Mode,
    affordable,
)
from wrenholt.gateway.retry import GuardedPolicy
from wrenholt.gateway.types import Message
from wrenholt.labs import fallback_lab as lab
from wrenholt.labs.agent_lab import Telemetry
from wrenholt.orchestrator.degraded import BRIEFS, HANDOFF, degrade
from wrenholt.rag.retriever import Found
from wrenholt.telemetry import conventions as c

A, B = "mock-a-fast", "mock-b-standard"
ASK = [Message("user", "How long do I have to return an item?")]
RETURNS = "How long do I have to return an item?"
REFUND = "Please refund £5.00 on order WG-100006."


async def no_wait(_: float) -> None:
    pass


def run(
    plan: FaultPlan,
    n: int = 1,
    every: int = 0,
    seconds: float | None = None,
    retired: bool = False,
) -> tuple[Telemetry, list[str], int, int]:
    """n calls for A, with B behind it; what answered each, and the
    requests each provider received."""
    t, got = Telemetry(), list[str]()
    with (
        running_provider(plan) as a,
        running_provider(provider="b") as b,
    ):
        # A retired fallback: provider A does not serve B's model.
        where = a.base_url if retired else b.base_url
        routes = {
            A: Route("wrenholt.mock_a", a.base_url, "x"),
            B: Route("wrenholt.mock_b", where, "x"),
        }

        async def go() -> None:
            gw = FallbackGateway(
                routes,
                GuardedPolicy(),
                tracer_provider=t.tracing,
                meter_provider=t.meters,
                sleep=no_wait,
                chains={A: [B]},
                every=every,
            )
            tracer = t.tracing.get_tracer("wrenholt.test")
            try:
                for _ in range(n):
                    with tracer.start_as_current_span("answer"):
                        try:
                            if seconds is None:
                                done = await gw.chat(A, ASK)
                            else:
                                with deadline(seconds):
                                    done = await gw.chat(A, ASK)
                        except ProviderError as err:
                            got.append(err.error_type.value)
                        else:
                            got.append(done.response_model)
            finally:
                await gw.aclose()

        asyncio.run(go())
        sent_a, sent_b = len(a.log), len(b.log)
    return t, got, sent_a, sent_b


def answers(t: Telemetry) -> list[dict[str, Any]]:
    return [dict(s.attributes or {}) for s in t.named("answer")]


def switches(t: Telemetry) -> list[dict[str, Any]]:
    return [
        dict(e.attributes or {})
        for s in t.named("answer")
        for e in s.events
        if e.name == c.FALLBACK_EVENT
    ]


def test_a_failing_provider_falls_back_and_comes_back() -> None:
    busy = FaultPlan(rate_limited_requests=3, retry_after_s=1)
    t, got, sent_a, sent_b = run(busy, n=2)
    assert got == ["mock-b-standard-2026-09", "mock-a-fast-2026-09"]
    assert (sent_a, sent_b) == (4, 1)  # three 429s, then A again
    first, second = answers(t)
    assert first[c.DEGRADED_MODE] == "fallback_model"
    assert first[c.DEGRADED_REASON] == "rate_limited"
    assert c.DEGRADED_MODE not in second
    assert switches(t) == [
        {
            c.FALLBACK_FROM: A,
            c.FALLBACK_TO: B,
            c.ERROR_TYPE: "rate_limited",
        }
    ]


def test_one_call_in_every_exercises_the_fallback() -> None:
    t, got, _, sent_b = run(NO_FAULTS, n=3, every=3)
    assert got[2] == "mock-b-standard-2026-09" and sent_b == 1
    third = answers(t)[2]
    assert third[c.DEGRADED_MODE] == "fallback_model"
    assert third[c.DEGRADED_REASON] == "exercise"
    # A retired fallback fails its exercise, and A answers.
    t, got, sent_a, sent_b = run(
        NO_FAULTS, n=3, every=3, retired=True
    )
    assert got == ["mock-a-fast-2026-09"] * 3 and sent_b == 0
    third = answers(t)[2]
    assert (third[c.DEGRADED_MODE], third[c.DEGRADED_REASON]) == (
        "full",
        "exercise",
    )
    assert switches(t) == [
        {
            c.FALLBACK_FROM: B,
            c.FALLBACK_TO: A,
            c.ERROR_TYPE: "invalid_request",
        }
    ]


def test_a_spent_deadline_does_not_fall_back() -> None:
    t, got, sent_a, sent_b = run(NO_FAULTS, seconds=0.0)
    assert (got, sent_a, sent_b, switches(t)) == (
        ["timeout"],
        0,
        0,
        [],
    )


def test_only_an_affordable_fallback_starts() -> None:
    prices, peak = load_prices(), Decimal("21.91")
    assert affordable(prices, A, B, peak, Decimal("60.00"))
    assert not affordable(
        prices, A, "mock-a-large", peak, Decimal(60)
    )
    with pytest.raises(ValueError, match="costs too much"):
        create_app(Settings(fallbacks={A: ["mock-a-large"]}))
    create_app(Settings(spend_per_hour="0"))  # no affordable peak


IN_FORCE = {
    "HC-0001": "returns-2026-03",
    "HC-0002": "refund-timing-2026-05",
    "HC-0004": "order-tracking-2026-01",
}


def hit(article: str, version: str, text: str = "") -> list[Found]:
    return [Found(article, version, 0.9, text)]


def test_the_ladder_without_a_model() -> None:
    t = Telemetry()
    tracer = t.tracing.get_tracer("wrenholt.test")
    track = "Every order shows its status under My orders."
    cases = [
        (hit("HC-0001", "returns-2026-03"), "interactive"),
        (
            hit("HC-0002", "refund-timing-2026-05", "Refunds now."),
            "x",
        ),
        (hit("HC-0004", "order-tracking-2026-01", track), "x"),
        (hit("HC-0001", "returns-2025-09"), "interactive"),  # stale
        ([], "interactive"),  # FS-08: no passage
        (hit("HC-0001", "returns-2026-03"), "critical_action"),
    ]
    got = []
    for found, cls in cases:
        with tracer.start_as_current_span("answer"):
            out = degrade(found, cls, IN_FORCE, "shed")
        got.append((out.mode, out.text))
    assert got == [
        (Mode.CACHED, BRIEFS["HC-0001"].text),
        (Mode.CITATION, "From our help centre: Refunds now."),
        (Mode.CITATION, f"From our help centre: {track}"),
        (Mode.HANDOFF, HANDOFF),
        (Mode.HANDOFF, HANDOFF),
        (Mode.HANDOFF, HANDOFF),
    ]
    marks = [
        (a[c.DEGRADED_MODE], a[c.DEGRADED_REASON]) for a in answers(t)
    ]
    assert marks[0] == ("cached", "shed") and len(marks) == 6


CLASSES = st.sampled_from(["interactive", "critical_action"])


@given(st.lists(st.tuples(st.booleans(), CLASSES), max_size=200))
def test_admission_keeps_its_reserve(
    ops: list[tuple[bool, str]],
) -> None:
    a, held = Admission(10, 3), 0
    for release, cls in ops:
        if release and held:
            a.release()
            held -= 1
            continue
        before = a.in_flight
        took = a.admit(cls)
        room = 10 if cls == "critical_action" else 7
        assert took == (before < room)
        held += took
        assert a.in_flight == held <= 10


def test_the_api_sheds_and_degrades_without_a_queue() -> None:
    with running_provider() as mock:
        full = Settings(provider_url=mock.base_url, max_answers=0)
        with TestClient(create_app(full)) as client:
            shed = client.post("/chat", json={"message": RETURNS})
            refund = client.post("/chat", json={"message": REFUND})
        sent = len(mock.log)
    assert (shed.status_code, shed.json()) == (
        200,
        {"answer": BRIEFS["HC-0001"].text},
    )
    assert refund.status_code == 503 and sent == 0
    assert refund.headers["retry-after"] == "5"
    down = "http://127.0.0.1:9/v1"  # A and B both refuse
    gone = Settings(
        provider_url=down, provider_b_url=down, retries_per_minute=0
    )
    with TestClient(create_app(gone)) as client:
        reply = client.post("/chat", json={"message": RETURNS})
    assert reply.json() == {"answer": BRIEFS["HC-0001"].text}


def test_the_lab_numbers() -> None:
    runs = lab.fs03_runs()
    rows = {
        name: (r.answers, r.failed, r.calls[lab.A], r.calls[lab.B])
        for name, r in runs.items()
    }
    assert rows["no fallback"] == (5200, 4805, 403, 0)
    assert rows["fallback B"] == (5200, 0, 399, 4809)
    assert rows["B retired"] == (5200, 4805, 403, 4805)
    for name in ("no fallback", "fallback B", "B retired"):
        assert round(runs[name].back or 0, 1) == 120.1
    r = runs["B retired, 1%"]
    assert (r.exercised, r.exercise_failed, r.failed) == (24, 24, 0)
    priced = [
        (m, times, round(cost, 2), ok)
        for m, times, cost, ok in lab.fs13()
    ]
    assert priced == [
        (lab.B, Decimal("2.5"), Decimal("54.76"), True),
        (lab.LARGE, Decimal(5), Decimal("109.53"), False),
    ]
    assert lab.surge(False) == lab.Surge(5760, 0, 3840, 987, 10.0)
    assert lab.surge(True) == lab.Surge(4342, 5254, 4, 4, 2.0)
    assert max(len(line) for line in lab.report()) <= 70
