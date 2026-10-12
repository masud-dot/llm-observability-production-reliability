"""Linnet as an agent (Chapters 4, 6, 8 and 9).

One invoke_agent span covers each answer. Linnet retrieves policy
passages first. A question that names an order gets a tool loop:
the model decides, Linnet's code runs the tools, and a guard ends
a loop that repeats itself or runs out of steps. The answer is then
written, whole or streamed, from the passages and the facts the
tools found, so a streamed answer keeps Chapter 8's timers.
"""

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass

from opentelemetry import metrics, trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from wrenholt.gateway import (
    Completion,
    Gateway,
    Message,
    ProviderError,
    StreamResult,
)
from wrenholt.gateway.context import prompt
from wrenholt.orchestrator.guard import (
    FINISHED,
    NO_TOOLS,
    REPEATED,
    STEP_LIMIT,
    LoopGuard,
)
from wrenholt.orchestrator.prompts import SUPPORT
from wrenholt.privacy.pseudonym import Keys, keys_from_env
from wrenholt.rag.retriever import Found, Retriever
from wrenholt.telemetry import conventions as c
from wrenholt.tools.orders import ORDER_ID, OrdersClient
from wrenholt.tools.toolbox import FINISH, SPECS, Toolbox

AGENT = "Linnet"
DESCRIPTION = "Customer-support assistant for Wrenholt Goods"
BUDGET = 150  # passage tokens, counted as words like the mock
SPAN = {
    c.OPERATION_NAME: c.INVOKE_AGENT,
    c.AGENT_NAME: AGENT,
    c.AGENT_DESCRIPTION: DESCRIPTION,
}


@dataclass(frozen=True)
class Answer:
    text: str
    completion: Completion


@dataclass(frozen=True)
class Packed:
    kept: list[str]
    used: int  # tokens, counted as words
    dropped: int


def pack(found: list[Found], budget: int) -> Packed:
    """Passages in rank order until the next would overflow the
    budget; that one and every later one are dropped."""
    kept: list[str] = []
    used = 0
    for f in found:
        passage = f"[{f.id} {f.version}] {f.text}"
        cost = len(passage.split())
        if used + cost > budget:
            break
        kept.append(passage)
        used += cost
    return Packed(kept, used, len(found) - len(kept))


@dataclass
class Run:
    """One invocation, as the agent's metrics count it."""

    id: str  # names this invocation's refunds; never exported
    inference_calls: int = 0
    tool_calls: int = 0
    stop: str = NO_TOOLS


class Linnet:
    def __init__(
        self,
        retriever: Retriever,
        *,
        guard: Callable[[], LoopGuard] = LoopGuard,
        toolbox: type[Toolbox] = Toolbox,
        budget: int = BUDGET,
        keys: Keys | None = None,
        tracer_provider: trace.TracerProvider | None = None,
        meter_provider: metrics.MeterProvider | None = None,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self.retriever = retriever
        self._guard, self._budget, self._new_id = (
            guard,
            budget,
            new_id,
        )
        self._tools = toolbox(
            AGENT,
            keys or keys_from_env(),
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
        )
        self._tracer = trace.get_tracer(
            "wrenholt.agent", tracer_provider=tracer_provider
        )
        meter = metrics.get_meter(
            "wrenholt.agent", meter_provider=meter_provider
        )
        self._duration = meter.create_histogram(
            c.AGENT_DURATION,
            unit="s",
            description="Agent invocation duration.",
            explicit_bucket_boundaries_advisory=c.AGENT_BUCKETS,
        )
        self._inference = meter.create_histogram(
            c.AGENT_INFERENCE_CALLS,
            unit="{inference_call}",
            description="Model calls per agent invocation.",
            explicit_bucket_boundaries_advisory=c.CALL_BUCKETS,
        )
        self._tool_calls = meter.create_histogram(
            c.AGENT_TOOL_CALLS,
            unit="{tool_call}",
            description="Tool calls per agent invocation.",
            explicit_bucket_boundaries_advisory=c.CALL_BUCKETS,
        )

    async def answer(
        self,
        gateway: Gateway,
        model: str,
        question: str,
        orders: OrdersClient | None = None,
    ) -> Answer:
        run, start = Run(self._new_id()), time.perf_counter()
        with self._tracer.start_as_current_span(
            f"{c.INVOKE_AGENT} {AGENT}",
            kind=SpanKind.INTERNAL,
            attributes=SPAN,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                messages = await self._prepare(
                    gateway, model, question, orders, run
                )
                run.inference_calls += 1
                with prompt(SUPPORT.name, SUPPORT.version):
                    completion = await gateway.chat(model, messages)
            except ProviderError as err:
                self._end(span, run, start, err)
                raise
            self._end(span, run, start)
        return Answer(completion.text, completion)

    async def stream_answer(
        self,
        gateway: Gateway,
        model: str,
        question: str,
        orders: OrdersClient | None,
        result: StreamResult,
    ) -> AsyncGenerator[str]:
        """The same answer, streamed. As in the gateway, the span is
        current only around awaits, never across a yield."""
        run, start = Run(self._new_id()), time.perf_counter()
        span = self._tracer.start_span(
            f"{c.INVOKE_AGENT} {AGENT}",
            kind=SpanKind.INTERNAL,
            attributes=SPAN,
        )
        failed: ProviderError | None = None
        left = False
        try:
            with attached(span):
                messages = await self._prepare(
                    gateway, model, question, orders, run
                )
            run.inference_calls += 1
            used = (SUPPORT.name, SUPPORT.version)
            chunks = gateway.stream(model, messages, used, result)
            try:
                while True:
                    with attached(span):
                        try:
                            piece = await anext(chunks)
                        except StopAsyncIteration:
                            break
                    yield piece
            finally:
                await chunks.aclose()
        except ProviderError as err:
            failed = err
            raise
        except (GeneratorExit, asyncio.CancelledError):
            left = True
            raise
        finally:
            gone = left or result.cancelled
            self._end(span, run, start, failed, cancelled=gone)
            span.end()

    async def _prepare(
        self,
        gateway: Gateway,
        model: str,
        question: str,
        orders: OrdersClient | None,
        run: Run,
    ) -> list[Message]:
        """Retrieval, then the tool loop if an order is named: the
        notes the answer is written from."""
        notes = [self._context(self.retriever.search(question))]
        if orders is not None and ORDER_ID.search(question):
            asked = messages_for(notes, question)
            notes += await self._gather(
                gateway, model, asked, orders, run
            )
        return messages_for(notes, question)

    async def _gather(
        self,
        gateway: Gateway,
        model: str,
        messages: list[Message],
        orders: OrdersClient,
        run: Run,
    ) -> list[str]:
        """The tool loop: the model decides, Linnet's code acts, and
        the guard ends a loop that repeats itself."""
        deciding = gateway.with_tools(SPECS, choice="required")
        guard = self._guard()
        facts: list[str] = []
        run.stop = STEP_LIMIT
        while guard.step():
            run.inference_calls += 1
            with prompt(SUPPORT.name, SUPPORT.version):
                step = await deciding.chat(model, messages)
            messages.append(Message("assistant", "", step.tool_calls))
            for call in step.tool_calls:
                if call.name == FINISH:
                    run.stop = FINISHED
                    return facts
                if guard.repeats(call):
                    run.stop = REPEATED
                    return facts
                run.tool_calls += 1
                done = await self._tools.run(call, run.id, orders)
                reply = Message(
                    "tool", done.content, tool_call_id=call.id
                )
                messages.append(reply)
                if done.fact and done.fact not in facts:
                    facts.append(done.fact)
            if not step.tool_calls:  # an answer, not a call
                run.stop = FINISHED
                return facts
        return facts

    def _context(self, found: list[Found]) -> str:
        """The passages that fit the budget, in a span that says how
        much was used and how many were dropped."""
        with self._tracer.start_as_current_span(
            "build context", kind=SpanKind.INTERNAL
        ) as span:
            packed = pack(found, self._budget)
            span.set_attributes(
                {
                    c.CONTEXT_BUDGET: self._budget,
                    c.CONTEXT_TOKENS: packed.used,
                    c.CONTEXT_DROPPED: packed.dropped,
                }
            )
        if not packed.kept:
            return ""
        return "Policy context:\n" + "\n".join(packed.kept)

    def _end(
        self,
        span: Span,
        run: Run,
        start: float,
        err: ProviderError | None = None,
        *,
        cancelled: bool = False,
    ) -> None:
        span.set_attribute(c.AGENT_STOP, run.stop)
        named = {c.AGENT_NAME: AGENT}
        self._inference.record(run.inference_calls, named)
        self._tool_calls.record(run.tool_calls, named)
        measured = {**named, c.AGENT_STOP: run.stop}
        if err is not None:
            span.set_attribute(c.ERROR_TYPE, err.error_type.value)
            span.set_status(Status(StatusCode.ERROR))
            measured[c.ERROR_TYPE] = err.error_type.value
        if not cancelled:  # a customer who left ended nothing
            took = time.perf_counter() - start
            self._duration.record(took, measured)


def attached(span: Span) -> AbstractContextManager[Span]:
    """Make the span current for one await; status is set by hand."""
    return trace.use_span(
        span,
        end_on_exit=False,
        record_exception=False,
        set_status_on_exception=False,
    )


def messages_for(notes: list[str], question: str) -> list[Message]:
    """The prompt, Linnet's notes and the question."""
    return [
        Message("system", SUPPORT.text),
        *(Message("system", n) for n in notes if n),
        Message("user", question),
    ]
