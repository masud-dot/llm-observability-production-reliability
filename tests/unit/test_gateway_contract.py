"""Gateway telemetry contract: names, kinds, links, attributes.

Real HTTP to the mock provider; in-memory exporters; no waiting
(the sleeps the gateway asks for are recorded instead).
"""

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import SpanKind, StatusCode

from services.mock_llm.faults import FS01_HIDDEN_RETRY_STORM
from services.mock_llm.server import running_provider
from wrenholt.gateway import Gateway, Message, ProviderError, Route
from wrenholt.telemetry import conventions as c

MODEL = "mock-a-fast"
ASK = [Message("user", "When will my refund arrive?")]


@dataclass
class Harness:
    spans: InMemorySpanExporter
    metrics: InMemoryMetricReader
    sleeps: list[float]

    def gateway(self, base_url: str) -> Gateway:
        tracing = TracerProvider()
        tracing.add_span_processor(SimpleSpanProcessor(self.spans))

        async def sleep(seconds: float) -> None:
            self.sleeps.append(seconds)

        return Gateway(
            {MODEL: Route("wrenholt.mock_a", base_url, "sk-mock")},
            tracer_provider=tracing,
            meter_provider=MeterProvider(
                metric_readers=[self.metrics]
            ),
            sleep=sleep,
            jitter=lambda: 0.0,
        )

    def points(
        self, name: str
    ) -> list[tuple[dict[str, object], float]]:
        found: list[tuple[dict[str, object], float]] = []
        data = self.metrics.get_metrics_data()
        for resource in data.resource_metrics if data else []:
            for scope in resource.scope_metrics:
                for metric in scope.metrics:
                    if metric.name != name:
                        continue
                    for p in metric.data.data_points:
                        value = getattr(p, "value", None)
                        if value is None:
                            value = getattr(p, "count", 0)
                        attrs: dict[str, object] = dict(
                            p.attributes or {}
                        )
                        found.append((attrs, float(value or 0)))
        return found


@pytest.fixture
def harness() -> Iterator[Harness]:
    yield Harness(InMemorySpanExporter(), InMemoryMetricReader(), [])


def ask(gateway: Gateway) -> object:
    async def go() -> object:
        try:
            return await gateway.chat(MODEL, ASK)
        except ProviderError as err:
            return err
        finally:
            await gateway.aclose()

    return asyncio.run(go())


def split(
    spans: tuple[ReadableSpan, ...],
) -> tuple[ReadableSpan, list[ReadableSpan]]:
    (request,) = [s for s in spans if s.name == f"chat {MODEL}"]
    tries = sorted(
        (s for s in spans if s.name == "attempt wrenholt.mock_a"),
        key=lambda s: (s.attributes or {})[c.ATTEMPT_NUMBER],
    )
    return request, tries


def test_fs01_every_attempt_is_a_child_span(harness: Harness) -> None:
    with running_provider(FS01_HIDDEN_RETRY_STORM) as mock:
        result = ask(harness.gateway(mock.base_url))
        seen = mock.log.items()
    assert not isinstance(result, ProviderError)
    request, tries = split(harness.spans.get_finished_spans())
    assert request.kind is SpanKind.CLIENT
    assert request.status.status_code is StatusCode.UNSET
    attrs = dict(request.attributes or {})
    assert attrs[c.OPERATION_NAME] == "chat"
    assert attrs[c.PROVIDER_NAME] == "wrenholt.mock_a"
    assert attrs[c.REQUEST_MODEL] == MODEL
    assert attrs[c.RESPONSE_MODEL] == "mock-a-fast-2026-09"
    assert attrs[c.SERVER_ADDRESS] == "127.0.0.1"
    assert attrs[c.ATTEMPT_COUNT] == 3
    assert c.ERROR_TYPE not in attrs
    assert [t.parent.span_id for t in tries if t.parent] == [
        request.context.span_id
    ] * 3
    assert {t.kind for t in tries} == {SpanKind.INTERNAL}
    a = [dict(t.attributes or {}) for t in tries]
    assert [x[c.HTTP_STATUS] for x in a] == [429, 429, 200]
    assert [x.get(c.ERROR_TYPE) for x in a] == [
        "rate_limited",
        "rate_limited",
        None,
    ]
    assert [x[c.ATTEMPT_DELAY] for x in a] == [0.0, 1.0, 1.0]
    assert [x.get(c.ATTEMPT_RETRY_AFTER) for x in a] == [
        1.0,
        1.0,
        None,
    ]
    assert harness.sleeps == [1.0, 1.0]  # retry-after honoured
    # SDK retries are off: every request is the SDK's first try.
    assert [r.retry_count for r in seen] == ["0", "0", "0"]


def test_fs18_quota_is_not_retried(harness: Harness) -> None:
    with running_provider(spend_cap=True) as mock:
        result = ask(harness.gateway(mock.base_url))
        seen = mock.log.items()
    assert isinstance(result, ProviderError)
    assert result.error_type == "quota_exhausted"
    request, tries = split(harness.spans.get_finished_spans())
    assert request.status.status_code is StatusCode.ERROR
    assert (request.attributes or {})[
        c.ERROR_TYPE
    ] == "quota_exhausted"
    (only,) = tries
    assert (only.attributes or {})[c.ATTEMPT_RETRYABLE] is False
    assert [r.status for r in seen] == [429]
    assert harness.sleeps == []


def test_metrics_count_attempts_and_time_requests(
    harness: Harness,
) -> None:
    with running_provider(FS01_HIDDEN_RETRY_STORM) as mock:
        ask(harness.gateway(mock.base_url))
    attempts = harness.points(c.ATTEMPTS)
    by_error = {str(a.get(c.ERROR_TYPE, "-")): v for a, v in attempts}
    assert by_error == {"rate_limited": 2, "-": 1}
    ((attrs, count),) = harness.points(c.OPERATION_DURATION)
    assert count == 1
    assert attrs[c.RESPONSE_MODEL] == "mock-a-fast-2026-09"
    assert c.ERROR_TYPE not in attrs


def test_unreachable_provider_is_provider_unavailable(
    harness: Harness,
) -> None:
    result = ask(harness.gateway("http://127.0.0.1:9/v1"))
    assert isinstance(result, ProviderError)
    assert result.error_type == "provider_unavailable"
    _, tries = split(harness.spans.get_finished_spans())
    assert len(tries) == 3  # retryable: the cap stops it
    assert len(harness.sleeps) == 2
