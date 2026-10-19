"""The guarded gateway (Chapter 16) against the mock provider, tool
calls under the deadline and the budget, and the lab's numbers."""

import asyncio
from collections.abc import Callable
from typing import Any

import pytest

from services.mock_llm.faults import NO_FAULTS, FaultPlan
from services.mock_llm.server import running_provider
from wrenholt.gateway import Gateway, RetryPolicy, Route
from wrenholt.gateway.deadlines import deadline
from wrenholt.gateway.errors import ErrorType, ProviderError, Rejected
from wrenholt.gateway.guarded import GuardedGateway
from wrenholt.gateway.openai_compat import OpenAICompatible
from wrenholt.gateway.retry import GuardedPolicy, RetryBudget
from wrenholt.gateway.types import Message
from wrenholt.labs import protect_lab as lab
from wrenholt.labs.agent_lab import Telemetry
from wrenholt.telemetry import conventions as c
from wrenholt.tools.errors import ToolError
from wrenholt.tools.guarded import GuardedOrders
from wrenholt.tools.orders import OrdersClient

MODEL = "mock-a-fast"
ASK = [Message("user", "Where is my refund?")]
A = "wrenholt.mock_a"
Prepare = Callable[[GuardedGateway], None]


def chat(
    policy: RetryPolicy,
    seconds: float | None = None,
    *,
    plan: FaultPlan = NO_FAULTS,
    guarded: bool = True,
    prepare: Prepare | None = None,
    spend_cap: bool = False,
) -> tuple[Telemetry, int, list[float], ProviderError | None]:
    """One chat call; the provider requests it caused, the waits."""
    t, waits = Telemetry(), list[float]()

    async def sleep(s: float) -> None:
        waits.append(s)

    with running_provider(plan, spend_cap=spend_cap) as mock:
        route = Route(A, mock.base_url, "sk-mock")
        kind = GuardedGateway if guarded else Gateway

        async def go() -> ProviderError | None:
            gw = kind(
                {MODEL: route},
                policy,
                tracer_provider=t.tracing,
                meter_provider=t.meters,
                sleep=sleep,
            )
            if prepare is not None and isinstance(gw, GuardedGateway):
                prepare(gw)
            try:
                if seconds is None:
                    await gw.chat(MODEL, ASK)
                else:
                    with deadline(seconds):
                        await gw.chat(MODEL, ASK)
            except ProviderError as err:
                return err
            finally:
                await gw.aclose()
            return None

        err = asyncio.run(go())
        sent = len(mock.log)
    return t, sent, waits, err


def decided(t: Telemetry) -> list[Any]:
    (span,) = t.named(f"{c.CHAT} ")
    return [
        dict(e.attributes or {})
        for e in span.events
        if e.name == c.RETRY_EVENT
    ]


def test_a_retry_after_that_fits_the_deadline_is_waited() -> None:
    six = FaultPlan(rate_limited_requests=1, retry_after_s=6)
    _, sent, waits, err = chat(RetryPolicy(), plan=six, guarded=False)
    assert (sent, waits, err and err.error_type) == (
        1,
        [],
        ErrorType.RATE_LIMITED,
    )
    t, sent, waits, err = chat(GuardedPolicy(), 9.0, plan=six)
    assert (sent, waits, err) == (2, [6.0], None)
    (event,) = decided(t)
    assert event[c.RETRY_DECISION] == "retry"
    assert event[c.RETRY_WAIT] == 6.0
    assert 8.9 < event[c.DEADLINE_LEFT] <= 9.0
    t, sent, _, err = chat(GuardedPolicy(), 5.0, plan=six)
    assert (
        sent == 1 and err and err.error_type is ErrorType.RATE_LIMITED
    )
    assert decided(t)[0][c.RETRY_DECISION] == "deadline"


def open_breaker(gw: GuardedGateway) -> None:
    for _ in range(5):
        gw.breakers[A].allow()
        gw.breakers[A].record(ErrorType.PROVIDER_UNAVAILABLE)


def fill(gw: GuardedGateway) -> None:
    gw.limits[A].in_flight = gw.limits[A].size


@pytest.mark.parametrize(
    ("prepare", "seconds", "kind", "reason"),
    [
        (
            open_breaker,
            None,
            ErrorType.PROVIDER_UNAVAILABLE,
            "breaker_open",
        ),
        (fill, None, ErrorType.OVERLOADED, "limit_full"),
        (None, 0.0, ErrorType.TIMEOUT, "deadline"),
    ],
)
def test_a_refusal_sends_nothing_and_is_recorded(
    prepare: Prepare | None,
    seconds: float | None,
    kind: ErrorType,
    reason: str,
) -> None:
    t, sent, _, err = chat(GuardedPolicy(), seconds, prepare=prepare)
    assert isinstance(err, Rejected) and not err.retryable
    assert (sent, err.error_type, err.reason) == (0, kind, reason)
    assert t.named("attempt ") == []
    (span,) = t.named(f"{c.CHAT} ")
    attrs = span.attributes or {}
    assert attrs[c.ERROR_TYPE] == kind.value
    assert attrs[c.RETRY_DECISION] == reason


def test_fs18_a_quota_is_neither_retried_nor_counted() -> None:
    def keep(gw: GuardedGateway) -> None:
        kept.append(gw)

    kept: list[GuardedGateway] = []
    t, sent, _, err = chat(
        GuardedPolicy(), spend_cap=True, prepare=keep
    )
    assert sent == 1 and err
    assert err.error_type is ErrorType.QUOTA_EXHAUSTED
    assert decided(t)[0][c.RETRY_DECISION] == "not_retryable"
    assert kept[0].breakers[A].state.value == "closed"


def test_an_attempt_ends_at_the_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def slow(*_: object) -> None:
        await asyncio.sleep(5)

    monkeypatch.setattr(OpenAICompatible, "chat", slow)
    t = Telemetry()
    route = Route(A, "http://127.0.0.1:9/v1", "sk-mock")

    async def go() -> None:
        gw = GuardedGateway(
            {MODEL: route},
            GuardedPolicy(),
            tracer_provider=t.tracing,
            meter_provider=t.meters,
        )
        try:
            with deadline(0.05), pytest.raises(ProviderError) as got:
                await gw.chat(MODEL, ASK)
            assert got.value.error_type is ErrorType.TIMEOUT
        finally:
            await gw.aclose()

    asyncio.run(go())
    (attempt,) = t.named("attempt ")
    assert (attempt.attributes or {})[c.ERROR_TYPE] == "timeout"
    assert decided(t)[0][c.RETRY_DECISION] == "deadline"


def test_tool_calls_keep_the_deadline_and_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[str] = []

    async def slow(
        _: object, order: str, amount: int, key: str
    ) -> None:
        sent.append(key)
        await asyncio.sleep(5)

    monkeypatch.setattr(OrdersClient, "refund", slow)

    async def go(per_minute: int) -> list[str]:
        orders = GuardedOrders(
            "http://127.0.0.1:9", RetryBudget(per_minute)
        )
        outcomes = []
        for _ in range(2):  # Chapter 9's call and its one retry
            with deadline(0.05), pytest.raises(ToolError) as got:
                await orders.refund("WG-100006", 500, "key-1")
            outcomes.append(got.value.args[0])
        return outcomes

    assert asyncio.run(go(0)) and sent == ["key-1"]
    sent.clear()
    asyncio.run(go(1))
    assert sent == ["key-1", "key-1"]


def test_the_lab_numbers() -> None:
    fs01 = lab.fs01()
    assert [(r.calls, r.failed) for r in fs01.values()] == [
        (2995, 290),
        (2460, 300),
    ]
    fs03 = lab.fs03()
    during = [
        sum(n for s, n in r.per_second.items() if s < 100)
        for r in fs03.values()
    ]
    assert during == [11928, 4120, 8]
    assert [r.failed for r in fs03.values()] == [3947, 4000, 4805]
    breaker = fs03["budget+breaker"]
    assert sum(t >= 100 for t in breaker.refused) == 805
    assert [s for _, s in breaker.states] == [
        "closed",
        "open",
        *["half_open", "open"] * 3,
        "half_open",
        "closed",
    ]
    assert dict(lab.decisions()) == {
        "retry-after 6.0 s": "retry in 6.0 s",
        "  chapter 4": "stop",
        "retry-after 9.5 s": "deadline",
        "FS-18 quota": "not_retryable",
        "  breaker after 10": "closed",
    }
    t = lab.timeout()
    assert (round(t["p99.9"], 2), t["timeout"]) == (1.87, 1.9)
    assert 0.0009 < t["false next day"] < 0.0011
    assert lab.bulkhead(0.4, 64) == (2400, 0)
    assert lab.bulkhead(3.0, 64) == (1280, 1120)
    assert (
        "gen_ai_client_operation_duration_seconds_bucket" in lab.QUERY
    )
    lines = lab.report()
    assert lines[-1].endswith("= 2.2 s")
    assert max(len(line) for line in lines) <= 70
