"""Linnet as an agent (Chapter 9): one span tree per answer."""

import asyncio

from opentelemetry.sdk.trace import ReadableSpan

from services.mock_llm.server import running_provider
from services.mock_llm.streaming import Schedule
from wrenholt.gateway import Gateway, Route, StreamResult
from wrenholt.labs.agent_lab import EMBED_1, Setup, Telemetry, ask
from wrenholt.orchestrator.linnet import Linnet
from wrenholt.rag.index import index_as_of
from wrenholt.rag.retriever import Retriever
from wrenholt.telemetry import conventions as c

REFUND = "Please refund £5.00 on order WG-100006."
POLICY = "How long do I have to return an item?"


def parent(span: ReadableSpan) -> int | None:
    return span.parent.span_id if span.parent else None


def test_a_refund_is_one_tree_under_invoke_agent() -> None:
    t = Telemetry()
    (answer,) = ask([REFUND], Setup(), t)
    (agent,) = t.named(c.INVOKE_AGENT)
    me = agent.context.span_id
    attrs = agent.attributes or {}
    assert agent.name == "invoke_agent Linnet"
    assert attrs[c.AGENT_STOP] == "finished"
    children = [
        s.name
        for s in t.spans.get_finished_spans()
        if parent(s) == me
    ]
    assert children == [
        "retrieval help-centre",
        "build context",
        "chat mock-a-fast",  # decides: look the order up
        "execute_tool lookup_order",
        "chat mock-a-fast",  # decides: refund
        "execute_tool issue_refund",
        "chat mock-a-fast",  # decides: finish
        "chat mock-a-fast",  # writes the answer
    ]
    decided = [
        (s.attributes or {})[c.FINISH_REASONS]
        for s in t.named("chat ")
    ]
    assert decided[:3] == [("tool_calls",)] * 3
    assert decided[3] == ("stop",)
    (calls,) = t.points(c.AGENT_INFERENCE_CALLS)
    (tools,) = t.points(c.AGENT_TOOL_CALLS)
    assert (calls.sum, tools.sum) == (4, 2)
    assert "£5.00" in answer.text


def test_a_policy_question_runs_no_loop() -> None:
    t = Telemetry()
    (answer,) = ask([POLICY], Setup(), t)
    (agent,) = t.named(c.INVOKE_AGENT)
    assert (agent.attributes or {})[c.AGENT_STOP] == "no_tools"
    (calls,) = t.points(c.AGENT_INFERENCE_CALLS)
    (tools,) = t.points(c.AGENT_TOOL_CALLS)
    assert (calls.sum, tools.sum) == (1, 0)
    assert answer.text == "Most items can be returned within 30 days."


def test_fs09_a_stale_index_misleads_a_sound_model() -> None:
    t = Telemetry()
    stale = Setup(index=index_as_of("2026-02-28", EMBED_1))
    (answer,) = ask([POLICY], stale, t)
    # The model repeated what retrieval gave it, faithfully.
    assert answer.text == "Most items can be returned within 60 days."
    (agent,) = t.named(c.INVOKE_AGENT)
    assert agent.status.is_ok


def streamed(leave_after: int | None) -> tuple[Telemetry, list[str]]:
    t = Telemetry()
    retriever = Retriever(
        index_as_of("2026-09-30", EMBED_1),
        EMBED_1,
        tracer_provider=t.tracing,
        meter_provider=t.meters,
    )
    linnet = Linnet(
        retriever, tracer_provider=t.tracing, meter_provider=t.meters
    )
    fast = Schedule(first_s=0.01, gap_s=0.01)
    with running_provider(streaming=fast) as mock:
        route = Route("wrenholt.mock_a", mock.base_url, "sk-mock")

        async def go() -> list[str]:
            gw = Gateway(
                {"mock-a-fast": route},
                tracer_provider=t.tracing,
                meter_provider=t.meters,
            )
            got: list[str] = []
            done = StreamResult()
            chunks = linnet.stream_answer(
                gw, "mock-a-fast", POLICY, None, done
            )
            try:
                async for piece in chunks:
                    got.append(piece)
                    if len(got) == leave_after:
                        break
            finally:
                await chunks.aclose()
                await gw.aclose()
            return got

        return t, asyncio.run(go())


def test_a_streamed_answer_keeps_its_parent() -> None:
    t, pieces = streamed(None)
    assert (
        "".join(pieces)
        == "Most items can be returned within 30 days."
    )
    (agent,) = t.named(c.INVOKE_AGENT)
    (chat,) = t.named("chat ")
    assert parent(chat) == agent.context.span_id
    (duration,) = t.points(c.AGENT_DURATION)
    assert duration.count == 1


def test_a_customer_who_leaves_ends_no_invocation() -> None:
    t, pieces = streamed(2)
    assert len(pieces) == 2
    (agent,) = t.named(c.INVOKE_AGENT)
    assert agent.status.is_ok  # leaving is not an error
    assert t.points(c.AGENT_DURATION) == []
    (calls,) = t.points(c.AGENT_INFERENCE_CALLS)
    assert calls.sum == 1  # the call it made still counts
