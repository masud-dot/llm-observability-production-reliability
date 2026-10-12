"""Fixtures for the comparison lab. Needs: uv sync --group lab"""

import os
from collections.abc import Iterator

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

os.environ["OTEL_SEMCONV_STABILITY_OPT_IN"] = (
    "gen_ai_latest_experimental,http"
)

try:
    from wrenholt.labs.layered import (
        instrument_default,
        uninstrument_default,
    )
except ImportError as exc:  # fail loudly, never skip silently
    raise pytest.UsageError(
        "tests/lab needs the lab group: uv sync --group lab"
    ) from exc


PROVIDERS: list[TracerProvider] = []


@pytest.fixture(scope="session")
def exporter() -> Iterator[InMemorySpanExporter]:
    spans = InMemorySpanExporter()
    PROVIDERS.append(instrument_default(spans))
    yield spans
    uninstrument_default()


@pytest.fixture
def tracer_provider(exporter: InMemorySpanExporter) -> TracerProvider:
    return PROVIDERS[0]  # the one the official instrumentation uses
