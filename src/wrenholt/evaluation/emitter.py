"""Evaluation results as telemetry (Chapter 13).

Each result becomes a `gen_ai.evaluation.result` event, parented to
the span of the request that produced the answer and naming the
completion by its response ID, and one count on a book-defined
counter that the quality SLIs and drift checks read. Neither carries
the question, the answer or an evaluator's explanation.
"""

from opentelemetry import _logs, metrics, trace
from opentelemetry.trace import NonRecordingSpan, SpanContext

from wrenholt.evaluation.evaluators import Evaluator, Sample, Verdict
from wrenholt.telemetry import conventions as c

# What the counter keeps besides name and label, within its budget.
SLICES = {
    "refusal": (c.PROMPT_VERSION,),
    "policy_accuracy": (c.INDEX_VERSION,),
}
Attrs = dict[str, str | float]


class ResultEmitter:
    def __init__(
        self,
        logger_provider: _logs.LoggerProvider | None = None,
        meter_provider: metrics.MeterProvider | None = None,
    ) -> None:
        self._events = _logs.get_logger(
            "wrenholt.evaluation", logger_provider=logger_provider
        )
        meter = metrics.get_meter(
            "wrenholt.evaluation", meter_provider=meter_provider
        )
        self._results = meter.create_counter(
            c.EVALUATION_RESULTS,
            unit="{result}",
            description="Evaluation results by evaluation and label.",
        )

    def start(
        self, evaluators: list[Evaluator], prompt: str, index: str
    ) -> None:
        """Every series at zero, as the API's SLI events are."""
        slices: dict[str, str] = {
            c.PROMPT_VERSION: prompt,
            c.INDEX_VERSION: index,
        }
        for e in evaluators:
            for label in e.labels:
                attrs = {
                    c.EVALUATION_NAME: e.name,
                    c.EVALUATION_LABEL: label,
                }
                for key in SLICES.get(e.name, ()):
                    attrs[key] = slices[key]
                self._results.add(0, attrs)

    def emit(
        self,
        evaluator: Evaluator,
        verdict: Verdict,
        sample: Sample,
        span: SpanContext,
        response_id: str | None = None,
        model: str | None = None,
    ) -> None:
        if verdict.label not in evaluator.labels:
            raise ValueError(
                f"{verdict.name}: no label {verdict.label}"
            )
        version = f"{evaluator.name}/{evaluator.version}"
        attrs: Attrs = {
            c.EVALUATION_NAME: verdict.name,
            c.EVALUATION_LABEL: verdict.label,
            c.EVALUATOR_VERSION: version,
            c.PROMPT_VERSION: sample.prompt_version,
            c.INDEX_VERSION: sample.index_version,
        }
        if verdict.score is not None:
            attrs[c.EVALUATION_SCORE] = verdict.score
        if response_id:
            attrs[c.RESPONSE_ID] = response_id
        if model:
            attrs[c.RESPONSE_MODEL] = model
        parent = trace.set_span_in_context(NonRecordingSpan(span))
        self._events.emit(
            event_name=c.EVALUATION_RESULT,
            context=parent,
            attributes=attrs,
        )
        kept: tuple[str, ...] = (
            c.EVALUATION_NAME,
            c.EVALUATION_LABEL,
        )
        kept += SLICES.get(verdict.name, ())
        self._results.add(1, {k: attrs[k] for k in kept})
