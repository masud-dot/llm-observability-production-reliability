"""FS-01: SDK-default retries collapse into one GenAI span.

These tests document a blind spot of default instrumentation.
They pass while the blind spot exists.
"""

from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from wrenholt.labs.fs01 import Fs01Result, SpanRow, run


def genai_spans(result: Fs01Result) -> list[SpanRow]:
    return [s for s in result.spans if s.name.startswith("chat ")]


def http_spans(result: Fs01Result) -> list[SpanRow]:
    return [s for s in result.spans if s.http_status is not None]


def test_default_retries_collapse_into_one_genai_span(
    exporter: InMemorySpanExporter,
) -> None:
    result = run(exporter, retries_on=True)
    (genai,) = genai_spans(result)
    attempts = http_spans(result)
    assert result.outcome.startswith("Refunds")
    assert [s.http_status for s in attempts] == [429, 429, 200]
    assert all(s.parent == genai.name for s in attempts)
    # The logical call succeeded: no error on the GenAI span and
    # no attribute that counts the attempts beneath it.
    assert genai.error_type is None
    assert genai.attempt_keys == ()
    assert genai.duration_ms >= 2000
    assert [r.status for r in result.provider] == [429, 429, 200]
    assert [r.retry_count for r in result.provider] == ["0", "1", "2"]


def test_with_sdk_retries_off_the_429_reaches_the_caller(
    exporter: InMemorySpanExporter,
) -> None:
    result = run(exporter, retries_on=False)
    (genai,) = genai_spans(result)
    assert result.outcome == "RateLimitError"
    assert genai.error_type == "RateLimitError"
    assert [s.http_status for s in http_spans(result)] == [429]
    assert [r.status for r in result.provider] == [429]
