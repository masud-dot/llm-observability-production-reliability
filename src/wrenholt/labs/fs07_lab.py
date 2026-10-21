"""FS-07 lab (Chapter 9): a refund that times out after it is made
(SIMULATED).

    uv run python scripts/fs07_duplicate_refund.py

The orders service holds back its answer to a new refund until
after Linnet's client has given up; the refund itself is already
made. Linnet retries once, first with a fresh key for every
request, then with one key per logical refund.
"""

import textwrap
import uuid
from dataclasses import dataclass

from opentelemetry.trace import Span

from services.orders.faults import Faults
from services.orders.store import OrderStore, generate_orders
from wrenholt.labs.agent_lab import Setup, Telemetry, ask
from wrenholt.telemetry import conventions as c
from wrenholt.tools.errors import ToolError, ToolErrorType
from wrenholt.tools.orders import OrdersClient
from wrenholt.tools.toolbox import (
    RefundArgs,
    Toolbox,
    ToolResult,
    refunded,
)

ORDER = "WG-100006"
QUESTION = f"Please refund £24.99 on order {ORDER}."
SLOW_S, TIMEOUT_S = 2.5, 2.0


class KeyPerRequest(Toolbox):
    """Before: a fresh key on every request, so the retry after a
    timeout is a second refund, not a question about the first."""

    async def _refund(
        self,
        orders: OrdersClient,
        args: RefundArgs,
        invocation: str,
        span: Span,
    ) -> ToolResult:
        order, amount = args.order_id, args.amount_minor
        try:
            done = await orders.refund(
                order, amount, uuid.uuid4().hex
            )
        except ToolError as err:
            if err.error_type is not ToolErrorType.TIMEOUT:
                raise
            done = await orders.refund(
                order, amount, uuid.uuid4().hex
            )
        span.set_attribute(c.TOOL_REPLAYED, done.replayed)
        return refunded(done)


@dataclass(frozen=True)
class Outcome:
    refunds: list[str]
    refunded_minor: int
    tool: str  # how the issue_refund span ended
    stop: str
    answer: str


def run(
    toolbox: type[Toolbox],
    slow_s: float = SLOW_S,
    timeout_s: float = TIMEOUT_S,
) -> Outcome:
    t = Telemetry()
    store = OrderStore(generate_orders())
    setup = Setup(
        toolbox=toolbox,
        faults=Faults(slow_commit_s=slow_s),
        timeout_s=timeout_s,
    )
    (answer,) = ask([QUESTION], setup, t, store)
    (tool,) = [
        s.attributes or {}
        for s in t.named(f"{c.EXECUTE_TOOL} issue_refund")
    ]
    if c.ERROR_TYPE in tool:
        ended = f"error {tool[c.ERROR_TYPE]}"
    else:
        ended = "replayed" if tool[c.TOOL_REPLAYED] else "made"
    (agent,) = t.named(c.INVOKE_AGENT)
    return Outcome(
        store.refunds_for(ORDER),
        store.refunded(ORDER),
        ended,
        str((agent.attributes or {})[c.AGENT_STOP]),
        answer.text,
    )


def main() -> None:
    before, after = run(KeyPerRequest), run(Toolbox)
    rows = [
        ("refunds made", len(before.refunds), len(after.refunds)),
        ("money refunded", f"£{before.refunded_minor / 100:.2f}",
         f"£{after.refunded_minor / 100:.2f}"),
        ("issue_refund span", before.tool, after.tool),
        ("stop reason", before.stop, after.stop),
    ]  # fmt: skip
    print("FS-07: a refund that times out after it is made")
    print("(mock provider and orders faults: SIMULATED)")
    print(f'"{QUESTION}"')
    print(f"Orders answers a new refund after {SLOW_S} s; Linnet")
    print(f"waits {TIMEOUT_S} s, then asks once more.")
    print(f"{'':<19}{'key per request':<17}key per refund")
    for label, a, b in rows:
        print(f"{label:<19}{a!s:<17}{b}")
    for label, run_ in (("request", before), ("refund", after)):
        print(f"customer, key per {label}:")
        print(textwrap.fill(run_.answer, 68, initial_indent="  ",
                            subsequent_indent="  "))  # fmt: skip
