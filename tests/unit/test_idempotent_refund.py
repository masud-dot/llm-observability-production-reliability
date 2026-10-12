"""Idempotent refunds (Chapter 9): one key per logical refund."""

import asyncio

from services.orders.app import create_app
from services.orders.store import OrderStore, generate_orders
from services.serving import serve
from wrenholt.gateway import ToolCall
from wrenholt.labs.agent_lab import Telemetry
from wrenholt.labs.fs07_lab import KeyPerRequest, run
from wrenholt.privacy.pseudonym import keys_from_env
from wrenholt.telemetry import conventions as c
from wrenholt.tools.orders import OrdersClient
from wrenholt.tools.toolbox import RefundArgs, Toolbox, refund_key

SLOW, PATIENCE = 0.6, 0.3  # seconds: the commit outlasts the client


def args(amount: int = 2499) -> RefundArgs:
    return RefundArgs(order_id="WG-100006", amount_minor=amount)


def test_the_key_names_the_logical_refund() -> None:
    assert refund_key("inv-1", args()) == refund_key("inv-1", args())
    assert refund_key("inv-1", args()) != refund_key("inv-2", args())
    assert refund_key("inv-1", args()) != refund_key(
        "inv-1", args(500)
    )


def test_fs07_a_key_per_request_pays_twice() -> None:
    before = run(KeyPerRequest, SLOW, PATIENCE)
    assert len(before.refunds) == 2
    assert before.refunded_minor == 2 * 2499
    assert before.tool == "error timeout"
    # The model asked again; the guard stopped the repeat.
    assert before.stop == "repeated_call"
    assert before.answer.startswith("I could not confirm")


def test_fs07_a_key_per_refund_pays_once() -> None:
    after = run(Toolbox, SLOW, PATIENCE)
    assert after.refunds == ["RF-000001"]
    assert after.refunded_minor == 2499
    assert after.tool == "replayed"  # the retry got the original
    assert after.stop == "finished"
    assert "RF-000001" in after.answer


def test_bad_arguments_never_reach_the_service() -> None:
    t = Telemetry()
    store = OrderStore(generate_orders())
    tools = Toolbox(
        "Linnet", keys_from_env(), tracer_provider=t.tracing
    )
    bad = ToolCall(
        "call_1",
        "issue_refund",
        '{"order_id": "WG-100006", "amount_minor": -5}',
    )
    with serve(create_app(store)) as url:

        async def go() -> str:
            orders = OrdersClient(url)
            try:
                done = await tools.run(bad, "inv-1", orders)
            finally:
                await orders.aclose()
            return done.content

        content = asyncio.run(go())
    assert content == '{"error": "invalid_arguments"}'
    assert store.refunds_for("WG-100006") == []
    (span,) = t.named(c.EXECUTE_TOOL)
    attrs = span.attributes or {}
    assert attrs[c.ERROR_TYPE] == "invalid_arguments"
    # The span holds a keyed fingerprint, never the arguments.
    assert str(attrs[c.TOOL_FINGERPRINT]).startswith("args:")
    assert "-5" not in str(dict(attrs))
