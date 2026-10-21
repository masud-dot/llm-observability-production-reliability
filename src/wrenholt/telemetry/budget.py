"""The cardinality guard (Chapter 10).

Wrenholt's MeterProvider is the SDK's with every meter wrapped: an
instrument that has a budget in the conventions module keeps only
its budgeted attributes, and a value outside a closed set becomes
_OTHER. The SDK's views can drop attributes but cannot map values,
so the guard wraps each budgeted instrument instead. Instruments
without a budget, such as the HTTP instrumentations', pass through
unchanged. A dropped attribute is logged once, by name only: its
value may be the identifier the budget keeps out.
"""

import logging
from collections.abc import Sequence

from opentelemetry import metrics
from opentelemetry.context import Context
from opentelemetry.metrics import CallbackT
from opentelemetry.sdk import metrics as sdk
from opentelemetry.util.types import Attributes

from wrenholt.telemetry import conventions as c

BUDGETS = {b.metric: b for b in c.BUDGET}
_log = logging.getLogger("wrenholt.telemetry.budget")
_warned: set[tuple[str, str]] = set()


def guard(metric: str, attributes: Attributes) -> Attributes:
    """What a measurement on this metric may keep."""
    budget = BUDGETS.get(metric)
    if budget is None or not attributes:
        return attributes
    for key in sorted(set(attributes) - set(budget.attributes)):
        if (metric, key) not in _warned:
            _warned.add((metric, key))
            _log.warning("%s: %s is not in its budget", metric, key)
    return {
        key: c.OTHER
        if key in c.CLOSED and value not in c.CLOSED[key]
        else value
        for key, value in attributes.items()
        if key in budget.attributes
    }


class _Counter(metrics.Counter):
    def __init__(self, inner: metrics.Counter, name: str) -> None:
        self._inner, self._metric = inner, name

    def add(
        self,
        amount: float,
        attributes: Attributes = None,
        context: Context | None = None,
    ) -> None:
        guarded = guard(self._metric, attributes)
        self._inner.add(amount, guarded, context)


class _UpDownCounter(metrics.UpDownCounter):
    def __init__(
        self, inner: metrics.UpDownCounter, name: str
    ) -> None:
        self._inner, self._metric = inner, name

    def add(
        self,
        amount: float,
        attributes: Attributes = None,
        context: Context | None = None,
    ) -> None:
        guarded = guard(self._metric, attributes)
        self._inner.add(amount, guarded, context)


class _Histogram(metrics.Histogram):
    def __init__(self, inner: metrics.Histogram, name: str) -> None:
        self._inner, self._metric = inner, name

    def record(
        self,
        amount: float,
        attributes: Attributes = None,
        context: Context | None = None,
    ) -> None:
        guarded = guard(self._metric, attributes)
        self._inner.record(amount, guarded, context)


class _Meter(metrics.Meter):
    """Creates instruments on the SDK's meter; wraps the budgeted."""

    def __init__(self, inner: metrics.Meter, name: str) -> None:
        super().__init__(name)
        self._inner = inner

    def create_counter(
        self, name: str, unit: str = "", description: str = ""
    ) -> metrics.Counter:
        made = self._inner.create_counter(name, unit, description)
        return _Counter(made, name) if name in BUDGETS else made

    def create_up_down_counter(
        self, name: str, unit: str = "", description: str = ""
    ) -> metrics.UpDownCounter:
        made = self._inner.create_up_down_counter(
            name, unit, description
        )
        if name in BUDGETS:
            return _UpDownCounter(made, name)
        return made

    def create_histogram(
        self,
        name: str,
        unit: str = "",
        description: str = "",
        *,
        explicit_bucket_boundaries_advisory: Sequence[float]
        | None = None,
    ) -> metrics.Histogram:
        made = self._inner.create_histogram(
            name,
            unit,
            description,
            explicit_bucket_boundaries_advisory=(
                explicit_bucket_boundaries_advisory
            ),
        )
        return _Histogram(made, name) if name in BUDGETS else made

    def create_gauge(
        self, name: str, unit: str = "", description: str = ""
    ) -> metrics._Gauge:
        return self._inner.create_gauge(name, unit, description)

    def create_observable_counter(
        self,
        name: str,
        callbacks: Sequence[CallbackT] | None = None,
        unit: str = "",
        description: str = "",
    ) -> metrics.ObservableCounter:
        return self._inner.create_observable_counter(
            name, callbacks, unit, description
        )

    def create_observable_gauge(
        self,
        name: str,
        callbacks: Sequence[CallbackT] | None = None,
        unit: str = "",
        description: str = "",
    ) -> metrics.ObservableGauge:
        return self._inner.create_observable_gauge(
            name, callbacks, unit, description
        )

    def create_observable_up_down_counter(
        self,
        name: str,
        callbacks: Sequence[CallbackT] | None = None,
        unit: str = "",
        description: str = "",
    ) -> metrics.ObservableUpDownCounter:
        return self._inner.create_observable_up_down_counter(
            name, callbacks, unit, description
        )


class MeterProvider(sdk.MeterProvider):
    """The SDK's MeterProvider, with the guard on every meter."""

    def get_meter(
        self,
        name: str,
        version: str | None = None,
        schema_url: str | None = None,
        attributes: Attributes = None,
    ) -> metrics.Meter:
        inner = super().get_meter(
            name, version, schema_url, attributes
        )
        return _Meter(inner, name)
