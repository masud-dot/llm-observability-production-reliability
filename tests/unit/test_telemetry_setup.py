"""Telemetry setup: opt-in, one owner, timeouts in seconds."""

import pytest
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)

from wrenholt.telemetry.framework import FRAMEWORK_TELEMETRY_OFF
from wrenholt.telemetry.setup import start_telemetry


def test_telemetry_is_off_without_an_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert start_telemetry() is None


def test_fastapi_builtin_telemetry_is_fully_off() -> None:
    assert set(FRAMEWORK_TELEMETRY_OFF.values()) == {False}
    assert len(FRAMEWORK_TELEMETRY_OFF) == 5


def test_python_exporter_reads_its_timeout_in_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The specification defines OTEL_EXPORTER_OTLP_TIMEOUT in
    # milliseconds. The pinned Python exporter (1.45.0) reads the
    # number as seconds, so "2000" would mean over half an hour.
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "2000")
    assert OTLPSpanExporter()._client._timeout == 2000.0
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "2")
    assert OTLPSpanExporter()._client._timeout == 2.0
