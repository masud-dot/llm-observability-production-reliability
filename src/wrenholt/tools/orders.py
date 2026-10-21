"""The orders service client: Linnet's tools call through it.

With telemetry on, the HTTP client instrumentation propagates
trace context, so the orders service's spans join Linnet's trace.
Only an order's status, date and total leave this module: the
customer's name, email, phone and address never do. Since
Chapter 9, failures are raised as tool errors, so each tool span
can say how its call ended.
"""

import re
from dataclasses import dataclass

import httpx2

from wrenholt.tools.errors import ToolError, ToolErrorType

ORDER_ID = re.compile(r"\bWG-\d{6}\b")


@dataclass(frozen=True)
class OrderFacts:
    order_id: str
    status: str
    placed_on: str
    total_minor: int = 0  # Chapter 9: refunds need the total


@dataclass(frozen=True)
class RefundReceipt:
    refund_id: str
    amount_minor: int
    replayed: bool  # the service had this key: the original refund


class OrdersClient:
    def __init__(self, base_url: str, timeout: float = 2.0) -> None:
        self._client = httpx2.AsyncClient(
            base_url=base_url, timeout=timeout
        )

    async def lookup(self, order_id: str) -> OrderFacts | None:
        """The order's facts, or None if there is no such order."""
        response = await self._send("GET", f"/orders/{order_id}")
        if response.status_code == 404:
            return None
        self._raise_for(response)
        data = response.json()
        return OrderFacts(
            data["order_id"],
            data["status"],
            data["placed_on"],
            data["total_minor"],
        )

    async def refund(
        self, order_id: str, amount_minor: int, key: str
    ) -> RefundReceipt:
        """One refund. The key is the caller's: the service answers
        a key it has seen with the refund it made then."""
        body = {"order_id": order_id, "amount_minor": amount_minor}
        response = await self._send(
            "POST", "/refunds", body, {"Idempotency-Key": key}
        )
        self._raise_for(response)
        data = response.json()
        return RefundReceipt(
            data["refund_id"],
            data["amount_minor"],
            data["replayed"],
        )

    async def _send(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx2.Response:
        try:
            return await self._client.request(
                method, path, json=body, headers=headers
            )
        except httpx2.TimeoutException as exc:
            raise ToolError(ToolErrorType.TIMEOUT) from exc
        except httpx2.HTTPError as exc:
            raise ToolError(ToolErrorType.UNAVAILABLE) from exc

    @staticmethod
    def _raise_for(response: httpx2.Response) -> None:
        if response.status_code >= 500:
            raise ToolError(ToolErrorType.UNAVAILABLE)
        if response.status_code >= 400:
            try:
                detail = str(response.json().get("detail", ""))
            except ValueError:
                detail = ""
            raise ToolError(ToolErrorType.REJECTED, detail)

    async def aclose(self) -> None:
        await self._client.aclose()
