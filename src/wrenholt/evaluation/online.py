"""Evaluating answers where they are served (Chapter 13).

Content stays in Linnet's process: the vault lets only investigators
read it (Chapter 7), so a sampled answer is evaluated here, while
its question, answer and passages are still in memory, and only the
results leave, as telemetry. The SIMULATED evaluators take
microseconds and run before the handler returns; a real judge would
take the same sample to a queue and run after it.
"""

import logging
from collections.abc import AsyncGenerator, Callable

from opentelemetry import trace

from wrenholt.evaluation.context import PASSAGES
from wrenholt.evaluation.emitter import ResultEmitter
from wrenholt.evaluation.evaluators import Evaluator, Sample
from wrenholt.evaluation.sampling import selected
from wrenholt.gateway import Gateway, StreamResult
from wrenholt.orchestrator.linnet import Answer
from wrenholt.slo.recorder import Screened
from wrenholt.tools.orders import OrdersClient

Versions = Callable[[], tuple[str, str]]  # prompt, index
LOG = logging.getLogger("wrenholt.evaluation")


class Evaluating:
    def __init__(
        self,
        inner: Screened,
        evaluators: list[Evaluator],
        results: ResultEmitter,
        rate: float,
        versions: Versions,
    ) -> None:
        self._inner, self._evaluators = inner, evaluators
        self._results, self._rate = results, rate
        self._versions = versions

    async def answer(
        self,
        gateway: Gateway,
        model: str,
        question: str,
        orders: OrdersClient | None = None,
    ) -> Answer:
        PASSAGES.set(())
        result = await self._inner.answer(
            gateway, model, question, orders
        )
        done = result.completion
        self._evaluate(
            question,
            result.text,
            done.response_id,
            done.response_model,
        )
        return result

    async def stream_answer(
        self,
        gateway: Gateway,
        model: str,
        question: str,
        orders: OrdersClient | None,
        result: StreamResult,
    ) -> AsyncGenerator[str]:
        PASSAGES.set(())
        sent: list[str] = []
        chunks = self._inner.stream_answer(
            gateway, model, question, orders, result
        )
        try:
            async for piece in chunks:
                sent.append(piece)
                yield piece
        finally:
            await chunks.aclose()
        # Only a stream that ended here; no response ID reaches it.
        model_seen = result.response_model
        self._evaluate(question, "".join(sent), None, model_seen)

    def _evaluate(
        self,
        question: str,
        text: str,
        response_id: str | None,
        model: str | None,
    ) -> None:
        span = trace.get_current_span().get_span_context()
        if not span.is_valid or not selected(
            span.trace_id, self._rate
        ):
            return
        prompt, index = self._versions()
        sample = Sample(question, text, PASSAGES.get(), prompt, index)
        for evaluator in self._evaluators:
            try:
                verdict = evaluator.evaluate(sample)
            except Exception:  # the sensor failed, not the answer
                LOG.warning("evaluation failed: %s", evaluator.name)
                continue
            if verdict is not None:
                self._results.emit(
                    evaluator,
                    verdict,
                    sample,
                    span,
                    response_id,
                    model,
                )
