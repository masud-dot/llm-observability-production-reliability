"""Redaction before export (Chapter 7).

One redactor serves two places: a filter on every handler of
Wrenholt's loggers, and a span processor that rewrites string
attributes as each span starts. Each replacement is counted.
"""

import logging
from collections.abc import Mapping
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.context import Context
from opentelemetry.metrics import MeterProvider
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace import (
    TracerProvider as SDKTracerProvider,
)

from wrenholt.privacy.classify import IDENTIFIERS, find
from wrenholt.privacy.pseudonym import Keys, keys_from_env, pseudonym
from wrenholt.telemetry import conventions as c


class Redactor:
    def __init__(
        self, keys: Keys, meter_provider: MeterProvider | None = None
    ) -> None:
        self.keys = keys
        meter = metrics.get_meter(
            "wrenholt.privacy", meter_provider=meter_provider
        )
        self._count = meter.create_counter(
            c.REDACTIONS,
            unit="{redaction}",
            description="Values replaced before export.",
        )

    def text(self, value: str, where: str) -> str:
        found = find(value)
        if not found:
            return value
        out, last = [], 0
        for f in found:
            raw = value[f.start : f.end]
            if f.kind in IDENTIFIERS:
                swap = f"[{pseudonym(f.kind, raw, self.keys)}]"
            else:
                swap = f"[{f.kind}]"
            out += [value[last : f.start], swap]
            last = f.end
            self._count.add(
                1, {c.PRIVACY_KIND: f.kind, c.PRIVACY_WHERE: where}
            )
        out.append(value[last:])
        return "".join(out)


class LogFilter(logging.Filter):
    """Redact the message and Wrenholt's own extra attributes."""

    def __init__(self, redactor: Redactor) -> None:
        super().__init__()
        self._redactor = redactor

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        clean = self._redactor.text(message, "log")
        if clean != message:
            record.msg, record.args = clean, ()
        for key, value in list(vars(record).items()):
            if key.startswith("wrenholt.") and isinstance(value, str):
                setattr(
                    record, key, self._redactor.text(value, "log")
                )
        return True


class SpanRedactor(SpanProcessor):
    """Redact string attributes on every span: those present at
    start, and any set later. The HTTP server instrumentation sets
    url.path after start, and paths carry order IDs."""

    def __init__(self, redactor: Redactor) -> None:
        self._redactor = redactor

    def _clean(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._redactor.text(value, "span")
        return value

    def on_start(
        self, span: Span, parent_context: Context | None = None
    ) -> None:
        for key, value in dict(span.attributes or {}).items():
            if self._clean(value) != value:
                span.set_attribute(key, self._clean(value))
        set_one, set_many = span.set_attribute, span.set_attributes

        def one(key: str, value: Any) -> None:
            set_one(key, self._clean(value))

        def many(items: Mapping[str, Any]) -> None:
            set_many({k: self._clean(v) for k, v in items.items()})

        setattr(span, "set_attribute", one)  # noqa: B010
        setattr(span, "set_attributes", many)  # noqa: B010

    def on_end(self, span: ReadableSpan) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def protect(logger: str = "wrenholt") -> Redactor:
    """Install redaction on every handler of Wrenholt's loggers and,
    when tracing is on, on every span. Call after instrument()."""
    redactor = Redactor(keys_from_env())
    for handler in logging.getLogger(logger).handlers:
        handler.addFilter(LogFilter(redactor))
    provider: Any = trace.get_tracer_provider()
    if isinstance(provider, SDKTracerProvider):
        provider.add_span_processor(SpanRedactor(redactor))
    return redactor
