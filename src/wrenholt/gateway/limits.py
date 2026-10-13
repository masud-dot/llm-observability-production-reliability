"""Per-tenant consumption limits (Chapter 11).

Every gateway call is charged to a tenant. Once a tenant's spend in
the current clock hour reaches its limit, the gateway refuses that
tenant's calls until the hour turns, so a runaway loop or a flood
of requests costs at most about one hour's limit: OWASP LLM10:2025
calls the attack on this denial of wallet. A tenant without a limit
is refused. A call admitted under the limit may end above it; the
next one is refused. The ledger lives in memory, so each instance
enforces its own limit.
"""

import time
from collections.abc import Callable, Mapping
from decimal import Decimal

HOUR = 3600


class LimitExceeded(Exception):
    """A call refused before it reached any provider."""

    def __init__(self, tenant: str, retry_after: float) -> None:
        super().__init__(f"{tenant}: spend limit reached")
        self.tenant, self.retry_after = tenant, retry_after


class Ledger:
    """Spend per tenant in the current clock hour, in US dollars."""

    def __init__(
        self,
        limits: Mapping[str, Decimal],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.limits = dict(limits)
        self._clock = clock
        self._hour = -1
        self._spent: dict[str, Decimal] = {}

    def _now(self) -> float:
        now = self._clock()
        hour = int(now // HOUR)
        if hour != self._hour:  # every tenant starts the hour at 0
            self._hour, self._spent = hour, {}
        return now

    def spent(self, tenant: str) -> Decimal:
        self._now()
        return self._spent.get(tenant, Decimal(0))

    def admit(self, tenant: str) -> None:
        limit = self.limits.get(tenant)
        if limit is None or self.spent(tenant) >= limit:
            raise LimitExceeded(tenant, HOUR - self._now() % HOUR)

    def charge(self, tenant: str, cost: Decimal) -> None:
        self._spent[tenant] = self.spent(tenant) + cost
