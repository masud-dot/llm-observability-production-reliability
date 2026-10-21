"""Evaluation results as telemetry (Chapter 13): sampling, the
evaluators and their adapter, the emitter's linkage, the online
wrapper and the drift checks on synthetic series."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any, cast

import pytest
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import SpanContext, TraceFlags

from wrenholt.evaluation import sampling
from wrenholt.evaluation.context import PASSAGES
from wrenholt.evaluation.drift import Mix, Rate, mix_shift, rate_shift
from wrenholt.evaluation.emitter import ResultEmitter
from wrenholt.evaluation.evaluators import (
    External,
    Groundedness,
    Intent,
    PolicyAccuracy,
    Refusal,
    Sample,
    standard,
    window_in_force,
)
from wrenholt.evaluation.online import Evaluating
from wrenholt.gateway import Completion, Gateway, StreamResult
from wrenholt.guardrail import REFUSAL
from wrenholt.orchestrator.linnet import Answer
from wrenholt.slo.recorder import Screened
from wrenholt.telemetry import conventions as c

POLICY = "How long do I have to return an item?"
PASSAGE = "Most items can be returned within 30 days of delivery."


def sample(answer: str, question: str = POLICY) -> Sample:
    return Sample(question, answer, (PASSAGE,), "1", "index-1")


class Telemetry:
    def __init__(self) -> None:
        self.logs = InMemoryLogRecordExporter()  # type: ignore[no-untyped-call]
        provider = LoggerProvider()
        provider.add_log_record_processor(
            SimpleLogRecordProcessor(self.logs)
        )
        self.reader = InMemoryMetricReader()
        meters = MeterProvider(metric_readers=[self.reader])
        self.results = ResultEmitter(provider, meters)

    def counts(self) -> dict[tuple[tuple[str, Any], ...], float]:
        data = self.reader.get_metrics_data()
        return {
            tuple(sorted((p.attributes or {}).items())): cast(
                Any, p
            ).value
            for r in (data.resource_metrics if data else [])
            for s in r.scope_metrics
            for m in s.metrics
            if m.name == c.EVALUATION_RESULTS
            for p in m.data.data_points
        }


def test_sampling_is_the_trace_id_ratio_rule() -> None:
    low, high = 1, (1 << 64) - 1
    assert sampling.selected(low, 0.1) and not sampling.selected(
        high, 0.1
    )
    assert not sampling.selected(low, 0.0) and sampling.selected(
        high, 1.0
    )
    # the high 64 bits play no part, as in TraceIdRatioBased
    assert sampling.selected((7 << 64) | low, 0.1)
    ids = [
        (i * 0x9E3779B97F4A7C15) & ((1 << 128) - 1)
        for i in range(10000)
    ]
    share = sum(sampling.selected(i, 0.1) for i in ids) / len(ids)
    assert abs(share - 0.1) < 0.01
    with pytest.raises(ValueError):
        sampling.selected(1, 1.5)


def test_the_evaluators_on_known_answers() -> None:
    assert window_in_force() == 30
    right = sample("Most items can be returned within 30 days.")
    stale = sample("Most items can be returned within 60 days.")
    stale_seen = Sample(
        POLICY, stale.answer, ("returned within 60 days",), "1", "old"
    )
    assert Intent().evaluate(right).label == "policy"
    assert Groundedness().evaluate(right).label == "grounded"  # type: ignore[union-attr]
    assert Groundedness().evaluate(stale).label == "ungrounded"  # type: ignore[union-attr]
    # FS-09: grounded in what it retrieved, and wrong
    assert Groundedness().evaluate(stale_seen).label == "grounded"  # type: ignore[union-attr]
    accuracy = PolicyAccuracy(window_in_force())
    assert accuracy.evaluate(stale_seen).label == "incorrect"  # type: ignore[union-attr]
    assert Refusal().evaluate(sample(REFUSAL)).label == "refusal"
    hand_off = "I could not confirm your refund just now."
    assert Refusal().evaluate(sample(hand_off)).label == "answer"
    order = sample(
        "Order WG-100006 is delivered.", "Where is WG-100006?"
    )
    assert Intent().evaluate(order).label == "order"
    assert (
        Groundedness().evaluate(order) is None
    )  # not a policy answer
    assert accuracy.evaluate(order) is None  # states no window


def test_an_outside_evaluator_is_adapted_to_a_closed_set() -> None:
    def judge(_: Sample) -> dict[str, object]:
        return {
            "metric": "Relevance",
            "score": 4.0,
            "label": "relevant",
        }

    relevance = External(
        "relevance",
        "judge-2026-10",
        ("relevant", "not_relevant"),
        judge,
        {"relevant": "relevant", "irrelevant": "not_relevant"},
    )
    verdict = relevance.evaluate(sample("x"))
    assert (verdict.label, verdict.score) == ("relevant", 4.0)
    loose = External("relevance", "2", ("relevant",), judge, {})
    with pytest.raises(ValueError, match="unmapped"):
        loose.evaluate(sample("x"))


def test_an_event_is_linked_and_carries_no_content() -> None:
    t = Telemetry()
    judges = standard()
    t.results.start(judges, "1", "index-1")
    span = SpanContext(0xA1, 0xB2, False, TraceFlags(1))
    s = sample("Most items can be returned within 30 days.")
    for judge in judges:
        verdict = judge.evaluate(s)
        if verdict is not None:
            t.results.emit(
                judge, verdict, s, span, "chatcmpl-1", "m-1"
            )
    records = [r.log_record for r in t.logs.get_finished_logs()]
    assert {r.event_name for r in records} == {c.EVALUATION_RESULT}
    assert {(r.trace_id, r.span_id) for r in records} == {
        (0xA1, 0xB2)
    }
    first = dict(records[0].attributes or {})
    assert first == {
        c.EVALUATION_NAME: "intent",
        c.EVALUATION_LABEL: "policy",
        c.EVALUATOR_VERSION: "intent/1",
        c.PROMPT_VERSION: "1",
        c.INDEX_VERSION: "index-1",
        c.RESPONSE_ID: "chatcmpl-1",
        c.RESPONSE_MODEL: "m-1",
    }
    texts = {s.question, s.answer, PASSAGE}
    for r in records:
        assert r.body is None
        assert not texts & {
            str(v) for v in (r.attributes or {}).values()
        }
    names = [
        dict(r.attributes or {})[c.EVALUATION_NAME] for r in records
    ]
    assert names == [
        "intent",
        "refusal",
        "groundedness",
        "policy_accuracy",
    ]
    counts = t.counts()
    assert len(counts) == 10  # every series, at zero first
    refusal = (
        (c.EVALUATION_NAME, "refusal"),
        (c.EVALUATION_LABEL, "answer"),
        (c.PROMPT_VERSION, "1"),
    )
    assert counts[refusal] == 1  # sliced by prompt version only
    with pytest.raises(ValueError):
        bad = Refusal().evaluate(s)
        t.results.emit(Intent(), bad, s, span)


class Inner:
    """Linnet behind the guardrail, as far as the wrapper can tell."""

    async def answer(self, *_: object) -> Answer:
        PASSAGES.set((PASSAGE,))
        text = "Most items can be returned within 30 days."
        done = Completion(
            text, 200, "m-1", "chatcmpl-9", ("stop",), 1, 1
        )
        return Answer(text, done)

    async def stream_answer(self, *_: object) -> AsyncGenerator[str]:
        PASSAGES.set((PASSAGE,))
        for piece in (
            "Most items can be returned ",
            "within 30 days.",
        ):
            yield piece


INNER = cast(Screened, Inner())
NO_GATEWAY = cast(Gateway, None)


def test_the_wrapper_evaluates_a_sampled_request_in_its_span() -> (
    None
):
    t = Telemetry()
    tracer = TracerProvider().get_tracer("test")

    def run(rate: float, stream: bool = False) -> int:
        evaluating = Evaluating(
            INNER,
            standard(),
            t.results,
            rate,
            lambda: ("3", "index-2"),
        )

        async def go() -> None:
            if stream:
                done = StreamResult(response_model="m-1")
                async for _ in evaluating.stream_answer(
                    NO_GATEWAY, "m", POLICY, None, done
                ):
                    pass
            else:
                await evaluating.answer(NO_GATEWAY, "m", POLICY)

        before = len(t.logs.get_finished_logs())
        with tracer.start_as_current_span("POST /chat") as span:
            asyncio.run(go())
        records = [
            r.log_record for r in t.logs.get_finished_logs()[before:]
        ]
        ctx = span.get_span_context()
        assert all(
            (r.trace_id, r.span_id) == (ctx.trace_id, ctx.span_id)
            for r in records
        )
        return len(records)

    assert run(1.0) == 4  # intent, refusal, groundedness, accuracy
    assert run(0.0) == 0  # not sampled
    assert run(1.0, stream=True) == 4
    streamed = dict(
        t.logs.get_finished_logs()[-1].log_record.attributes or {}
    )
    assert c.RESPONSE_ID not in streamed  # a stream has none
    assert streamed[c.PROMPT_VERSION] == "3"

    # an evaluator that fails costs the answer nothing
    def broken(_: Sample) -> dict[str, object]:
        raise TimeoutError("judge")

    judge = External("judge", "1", ("pass",), broken, {})
    failing = Evaluating(
        INNER, [judge], t.results, 1.0, lambda: ("1", "i")
    )
    with tracer.start_as_current_span("POST /chat"):
        text = asyncio.run(
            failing.answer(NO_GATEWAY, "m", POLICY)
        ).text
    assert text.startswith("Most items")
    # no request span, nothing to link: no evaluation
    evaluating = Evaluating(
        INNER, standard(), t.results, 1.0, lambda: ("1", "i")
    )
    before = len(t.logs.get_finished_logs())
    asyncio.run(evaluating.answer(NO_GATEWAY, "m", POLICY))
    assert len(t.logs.get_finished_logs()) == before


SENSOR = "refusal/1"


def test_a_rate_shift_waits_for_enough_results() -> None:
    week = Rate(0, 2016, SENSOR)
    assert rate_shift(week, Rate(7, 24, SENSOR)) is None  # 24 < 30
    found = rate_shift(week, Rate(9, 36, SENSOR))
    assert found is not None and found.flagged
    assert round(found.statistic, 1) == 22.5


def test_a_stable_series_is_not_flagged() -> None:
    base = Rate(20, 2000, SENSOR)  # 1 per cent
    for hours in range(3, 30):
        now = Rate(round(12 * hours * 0.01), 12 * hours, SENSOR)
        shift = rate_shift(base, now)
        assert shift is not None and not shift.flagged


def test_a_new_evaluator_is_a_new_baseline() -> None:
    with pytest.raises(ValueError, match="new baseline"):
        rate_shift(
            Rate(0, 100, "refusal/1"), Rate(30, 100, "refusal/2")
        )
    with pytest.raises(ValueError, match="new baseline"):
        mix_shift(
            Mix({"a": 50}, "intent/1"), Mix({"a": 50}, "intent/2")
        )


def test_mix_drift_on_synthetic_mixes() -> None:
    normal = {"policy": 6, "order": 3, "refund": 3}
    base = Mix({k: v * 168 for k, v in normal.items()}, "intent/1")
    same = Mix({k: v * 3 for k, v in normal.items()}, "intent/1")
    found = mix_shift(base, same)
    assert (
        found is not None
        and found.statistic == 0
        and not found.flagged
    )
    sale = {"policy": 4, "order": 7, "refund": 2, "other": 3}
    shifted = mix_shift(
        base, Mix({k: v * 2 for k, v in sale.items()}, "intent/1")
    )
    assert shifted is not None and shifted.flagged
    assert shifted.statistic == pytest.approx(0.375)
    assert mix_shift(base, Mix(sale, "intent/1")) is None  # 16 < 30
