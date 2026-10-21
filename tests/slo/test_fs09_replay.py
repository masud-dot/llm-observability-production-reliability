"""FS-09 replayed against the live retriever (Chapter 9): the
freshness SLI from retrieval spans, not from hand-built events."""

from collections.abc import Mapping, Sequence
from typing import cast

from wrenholt.labs.agent_lab import EMBED_1, Telemetry
from wrenholt.rag.index import index_as_of
from wrenholt.rag.retriever import Retriever
from wrenholt.slo.catalog import load_catalog
from wrenholt.slo.events import RequestEvent
from wrenholt.slo.fs09 import CONTEXT, policy_version
from wrenholt.slo.sli import measure
from wrenholt.telemetry import conventions as c

QUESTIONS = [
    "How long do I have to return an item?",
    "Can I return this?",
    "What is your returns window?",
    "When will my refund arrive?",  # relies on no returns policy
]


def freshness(as_of: str) -> tuple[int, int]:
    t = Telemetry()
    retriever = Retriever(
        index_as_of(as_of, EMBED_1),
        EMBED_1,
        tracer_provider=t.tracing,
    )
    for question in QUESTIONS:
        retriever.search(question)
    events = [
        RequestEvent(
            "policy_question",
            "interactive",
            "ok",
            policy_version=policy_version(
                cast(
                    Sequence[Mapping[str, object]],
                    (s.attributes or {})[c.RETRIEVAL_DOCUMENTS],
                )
            ),
        )
        for s in t.named(f"{c.RETRIEVAL} ")
    ]
    spec = load_catalog().get("policy_freshness")
    result = measure(spec, events, CONTEXT)
    return result.good, result.valid


def test_the_current_index_serves_the_policy_in_force() -> None:
    assert freshness("2026-09-30") == (3, 3)


def test_a_stale_index_fails_every_policy_answer() -> None:
    # Built before 1 March 2026: the 60-day window, superseded.
    assert freshness("2026-02-28") == (0, 3)
