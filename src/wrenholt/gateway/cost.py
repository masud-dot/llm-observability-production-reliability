"""Tokens and what they cost (Chapter 11).

The provider reports tokens; the price table turns them into money.
Prices are configuration with a version, never constants in code: a
provider changes its prices without changing its API. Tokens are
recorded under the GenAI names of the token-metric redesign
(Development at the pinned commit): counters for consumption, a
histogram for the size of one call. Cost is the book's own counter,
charged to the tenant whose call it was.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml
from opentelemetry import metrics

from wrenholt.gateway.types import Usage
from wrenholt.telemetry import conventions as c

PRICES = Path(__file__).with_name("prices.yaml")
MILLION = Decimal(1_000_000)
Attrs = dict[str, str | bool | int | float | list[str]]


@dataclass(frozen=True)
class Price:
    """US dollars per million tokens, for one model."""

    input: Decimal
    cached_input: Decimal
    output: Decimal

    def of(self, usage: Usage) -> Decimal:
        """One call's cost. Cached tokens are part of the input
        count, billed at the cached rate instead."""
        cached = usage.cache_read or 0
        fresh = usage.input - cached
        dollars = (
            fresh * self.input
            + cached * self.cached_input
            + usage.output * self.output
        )
        return dollars / MILLION


@dataclass(frozen=True)
class PriceTable:
    version: str
    prices: Mapping[str, Price]  # by requested model

    def missing(self, models: Iterable[str]) -> list[str]:
        """Routed models without a price."""
        return sorted(set(models) - set(self.prices))


def load_prices(path: Path = PRICES) -> PriceTable:
    raw = yaml.safe_load(path.read_text())
    if raw["currency"] != "USD":
        raise ValueError(f"{path.name}: prices must be in USD")
    prices = {
        model: Price(**{k: Decimal(str(v)) for k, v in row.items()})
        for model, row in raw["models"].items()
    }
    for model, p in prices.items():
        low = min(p.input, p.cached_input, p.output)
        if low < 0 or p.cached_input > p.input:
            raise ValueError(f"{path.name}: {model} looks wrong")
    return PriceTable(str(raw["version"]), prices)


class CostMeter:
    """Records what each completed call used, and what it cost."""

    def __init__(
        self, meter: metrics.Meter, table: PriceTable | None
    ) -> None:
        self.table = table
        self._input = meter.create_counter(
            c.USAGE_INPUT,
            unit="{token}",
            description="Input tokens, cached ones included.",
        )
        self._output = meter.create_counter(
            c.USAGE_OUTPUT,
            unit="{token}",
            description="Output tokens.",
        )
        self._cached = meter.create_counter(
            c.USAGE_CACHE_READ,
            unit="{token}",
            description="Input tokens read from the provider cache.",
        )
        self._per_call = meter.create_histogram(
            c.OUTPUT_PER_CALL,
            unit="{token}",
            description="Output tokens of one call.",
            explicit_bucket_boundaries_advisory=c.TOKEN_BUCKETS,
        )
        self._cost = meter.create_counter(
            c.COST,
            unit="{USD}",
            description="Provider cost, priced from the table.",
        )

    def record(
        self,
        route: Attrs,
        model: str,
        usage: Usage,
        tenant: str,
        version: str | None,
    ) -> Decimal | None:
        """Tokens always; cost when the table prices the requested
        model. route is the call's operation and route attributes."""
        tokens = {**route, c.RESPONSE_MODEL: model}
        tokens[c.TOKEN_MODALITY] = c.TEXT
        self._input.add(usage.input, tokens)
        self._output.add(usage.output, tokens)
        if usage.cache_read is not None:
            self._cached.add(usage.cache_read, tokens)
        self._per_call.record(usage.output, route)
        requested = str(route[c.REQUEST_MODEL])
        price = (
            self.table.prices.get(requested) if self.table else None
        )
        if price is None:
            return None
        cost = price.of(usage)
        charged: Attrs = {
            c.TENANT: tenant,
            c.PROVIDER_NAME: route[c.PROVIDER_NAME],
            c.REQUEST_MODEL: requested,
            c.RESPONSE_MODEL: model,
        }
        if version is not None:
            charged[c.PROMPT_VERSION] = version
        self._cost.add(float(cost), charged)
        return cost
