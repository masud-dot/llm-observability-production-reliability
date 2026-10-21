"""Off-the-shelf instrumentation, layered: the comparison lab.

This is not the book's telemetry design; Chapter 4 builds that
inside the gateway. The lab reproduces what a team gets by
switching on the official OpenAI instrumentation, which emits
GenAI spans, and the httpx2 client instrumentation, which emits
HTTP spans. It needs the `lab` group: uv sync --group lab
"""

import os

from opentelemetry.instrumentation.httpx import (
    HTTPX2ClientInstrumentor,
)
from opentelemetry.instrumentation.openai_v2 import (
    OpenAIInstrumentor,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
)

# Latest GenAI names plus stable HTTP names. Instrumentation
# libraries read this once, at the first instrument() call in the
# process, so it is set before that call.
OPT_IN_VAR = "OTEL_SEMCONV_STABILITY_OPT_IN"
OPT_IN = "gen_ai_latest_experimental,http"


def instrument_default(exporter: SpanExporter) -> TracerProvider:
    os.environ.setdefault(OPT_IN_VAR, OPT_IN)
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    OpenAIInstrumentor().instrument(tracer_provider=provider)
    HTTPX2ClientInstrumentor().instrument(tracer_provider=provider)
    return provider


def uninstrument_default() -> None:
    HTTPX2ClientInstrumentor().uninstrument()
    OpenAIInstrumentor().uninstrument()
