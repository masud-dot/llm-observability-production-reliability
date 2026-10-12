"""The vault's tiers and expiry; redaction in logs and spans."""

import logging
from typing import Any

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from wrenholt.privacy.pseudonym import parse_keys
from wrenholt.privacy.redact import LogFilter, Redactor, SpanRedactor
from wrenholt.privacy.vault import Reader, Vault

ANA = Reader("ana", "investigator", "wrenholt")
KEYS = parse_keys("k1:" + "11" * 32)


def test_vault_tiers_tenants_and_expiry() -> None:
    now = [1000.0]
    vault = Vault(ttl_s=60, clock=lambda: now[0])
    ref = vault.put(
        "t1", "wrenholt", {"question": "Where is WG-100006?"}
    )
    assert vault.read(ref, ANA, "FS-14 review") is not None
    assert (
        vault.read(ref, Reader("bo", "on-call", "wrenholt"), "x")
        is None
    )
    assert (
        vault.read("t1", Reader("cy", "investigator", "acme"), "x")
        is None
    )
    assert vault.read(ref, ANA, "") is None  # a reason is required
    now[0] += 61
    assert vault.read(ref, ANA, "too late") is None
    assert vault.purge() == 1 and vault.stored() == []
    outcomes = [row["outcome"] for row in vault.access_log()]
    assert outcomes == [
        "granted", "denied: role or reason", "denied: tenant",
        "denied: role or reason", "expired",
    ]  # fmt: skip
    assert "WG-100006" not in repr(vault.access_log())


def test_log_filter_redacts_message_and_extras() -> None:
    reader = InMemoryMetricReader()
    redactor = Redactor(KEYS, MeterProvider(metric_readers=[reader]))
    record = logging.LogRecord(
        "wrenholt.x", logging.INFO, __file__, 1,
        "asked by %s", ("jo@example.com",), None,
    )  # fmt: skip
    setattr(record, "wrenholt.note", "order WG-100006")  # noqa: B010
    LogFilter(redactor).filter(record)
    assert "jo@example.com" not in record.getMessage()
    assert "WG-100006" not in str(getattr(record, "wrenholt.note"))
    data = reader.get_metrics_data()
    assert data is not None
    (metric,) = data.resource_metrics[0].scope_metrics[0].metrics
    points: list[Any] = list(metric.data.data_points)
    assert sum(p.value for p in points) == 2


def test_span_redactor_covers_attributes_set_after_start() -> None:
    spans = InMemorySpanExporter()
    tracing = TracerProvider()
    tracing.add_span_processor(SpanRedactor(Redactor(KEYS)))
    tracing.add_span_processor(SimpleSpanProcessor(spans))
    tracer = tracing.get_tracer("t")
    with tracer.start_as_current_span(
        "GET", attributes={"url.full": "http://o/orders/WG-100006"}
    ) as span:
        span.set_attribute("url.path", "/orders/WG-100007")
        span.set_attributes({"note": "phone +44 7700 900628"})
    (done,) = spans.get_finished_spans()
    text = repr(dict(done.attributes or {}))
    for raw in ("WG-100006", "WG-100007", "+44 7700 900628"):
        assert raw not in text
    assert "[order_id:k1:" in text
