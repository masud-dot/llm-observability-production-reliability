"""Chapter 4 lab: official instrumentation versus the gateway.

These tests pin the gaps the gateway closes; the first two pass
while the official instrumentation has them.
"""

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from wrenholt.labs.gateway_lab import (
    attempts,
    gateway,
    genai,
    official,
    official_off,
)
from wrenholt.telemetry import conventions as c


def test_official_fs01_hides_attempts_and_the_server(
    exporter: InMemorySpanExporter,
) -> None:
    run = official(exporter, "fs01")
    attrs = genai(run).attributes or {}
    assert run.provider == (429, 429, 200)
    assert attempts(run) == []
    assert attrs[c.PROVIDER_NAME] == "openai"  # from the SDK
    assert c.SERVER_ADDRESS not in attrs


def test_official_fs18_retries_a_spent_quota(
    exporter: InMemorySpanExporter,
) -> None:
    run = official(exporter, "fs18")
    assert run.outcome == "RateLimitError"
    assert run.provider == (429, 429, 429)


def test_gateway_closes_both_gaps(
    exporter: InMemorySpanExporter, tracer_provider: TracerProvider
) -> None:
    with official_off(tracer_provider):
        fs01 = gateway(exporter, tracer_provider, "fs01")
        fs18 = gateway(exporter, tracer_provider, "fs18")
    attrs = genai(fs01).attributes or {}
    assert len(attempts(fs01)) == 3
    assert attrs[c.PROVIDER_NAME] == "wrenholt.mock_a"
    assert attrs[c.SERVER_ADDRESS] == "127.0.0.1"
    assert fs18.outcome == "quota_exhausted"
    assert fs18.provider == (429,)
