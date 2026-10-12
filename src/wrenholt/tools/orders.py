"""Order lookups (Chapter 6): Linnet's second downstream service.

With telemetry on, the HTTP client instrumentation propagates
trace context, so the orders service's spans join Linnet's trace.
Only the order's status and date reach the prompt: the customer's
name, email, phone and address never leave this module.
"""

import logging
import re
from dataclasses import dataclass

import httpx2

LOG = logging.getLogger("wrenholt.tools.orders")
ORDER_ID = re.compile(r"\bWG-\d{6}\b")


@dataclass(frozen=True)
class OrderFacts:
    order_id: str
    status: str
    placed_on: str


class OrdersClient:
    def __init__(self, base_url: str, timeout: float = 2.0) -> None:
        self._client = httpx2.AsyncClient(
            base_url=base_url, timeout=timeout
        )

    async def lookup(self, order_id: str) -> OrderFacts | None:
        try:
            response = await self._client.get(f"/orders/{order_id}")
        except httpx2.HTTPError:
            LOG.warning("orders lookup failed")
            return None
        if response.status_code != 200:
            return None
        data = response.json()
        return OrderFacts(
            data["order_id"], data["status"], data["placed_on"]
        )

    async def aclose(self) -> None:
        await self._client.aclose()
