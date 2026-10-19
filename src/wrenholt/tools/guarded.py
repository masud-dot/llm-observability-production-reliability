"""Tool calls under the request's deadline and the retry budget
(Chapter 16).

The orders service is called within whatever is left of the
request's deadline. A refund sent again with a key already sent is a
retry, Chapter 9's single one, and it spends from the same budget as
the gateway's retries; with the budget spent, it is not sent.
"""

import asyncio
from collections import deque
from collections.abc import Awaitable

from opentelemetry import trace

from wrenholt.gateway.deadlines import remaining
from wrenholt.gateway.retry import RetryBudget
from wrenholt.telemetry import conventions as c
from wrenholt.tools.errors import ToolError, ToolErrorType
from wrenholt.tools.orders import (
    OrderFacts,
    OrdersClient,
    RefundReceipt,
)


async def within[T](call: Awaitable[T]) -> T:
    left = remaining()
    if left is None:
        return await call
    try:
        async with asyncio.timeout(left):
            return await call
    except TimeoutError:
        raise ToolError(ToolErrorType.TIMEOUT, "deadline") from None


class GuardedOrders(OrdersClient):
    def __init__(
        self, base_url: str, budget: RetryBudget, timeout: float = 2.0
    ) -> None:
        super().__init__(base_url, timeout)
        self._budget = budget
        self._sent: deque[str] = deque(maxlen=1024)

    async def lookup(self, order_id: str) -> OrderFacts | None:
        return await within(super().lookup(order_id))

    async def refund(
        self, order_id: str, amount_minor: int, key: str
    ) -> RefundReceipt:
        if key in self._sent:
            spent = not self._budget.spend()
            decision = "budget_spent" if spent else "retry"
            trace.get_current_span().add_event(
                c.RETRY_EVENT, {c.RETRY_DECISION: decision}
            )
            if spent:
                raise ToolError(ToolErrorType.TIMEOUT, "budget spent")
        self._sent.append(key)
        return await within(
            super().refund(order_id, amount_minor, key)
        )
