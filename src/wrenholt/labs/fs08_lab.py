"""FS-08 lab (Chapter 9): empty retrieval after a re-index
(SIMULATED).

    uv run python scripts/fs08_empty_retrieval.py

The help-centre index is rebuilt with a new embedder while the
retriever still embeds questions with the old one. Vectors have
the same size, so nothing raises. Ten policy questions are asked
before and after the re-index, through a retriever without the
start-up check; then the check is tried on both indexes.
"""

import textwrap
from dataclasses import dataclass

from wrenholt.labs.agent_lab import EMBED_1, Setup, Telemetry, ask
from wrenholt.rag.corpus import TODAY
from wrenholt.rag.embed import EMBEDDERS, Embedder
from wrenholt.rag.index import Index, index_as_of
from wrenholt.rag.retriever import IndexMismatch, Retriever
from wrenholt.telemetry import conventions as c

QUESTIONS = [
    "How long do I have to return an item?",
    "Can I return this?",
    "What is your returns window?",
    "When will my refund arrive?",
    "How long does a refund take?",
    "My parcel arrived damaged, what can I do?",
    "How do I cancel my order?",
    "How do I track my order?",
    "How long is delivery to Keswick?",
    "Is there a warranty on the camping tent?",
]


class Unchecked(Retriever):
    """The retriever as it was: no start-up check."""

    @staticmethod
    def _check(index: Index, embedder: Embedder) -> None:
        return None


@dataclass(frozen=True)
class Outcome:
    index: str
    empty: int  # retrievals that returned no documents
    with_context: int  # answers whose prompt held a passage
    failed: int  # model calls that failed
    check: str  # the start-up check on this index


def check(index: Index) -> str:
    try:
        Retriever(index, EMBED_1)
    except IndexMismatch as exc:
        return f"refuses: {exc}"
    return "passes"


def run(embedder: Embedder) -> Outcome:
    t = Telemetry()
    index = index_as_of(TODAY, embedder)
    setup = Setup(index=index, retriever=Unchecked)
    ask(QUESTIONS, setup, t)
    retrievals = [
        s.attributes or {} for s in t.named(f"{c.RETRIEVAL} ")
    ]
    built = [s.attributes or {} for s in t.named("build context")]
    chats = [s for s in t.named(f"{c.CHAT} ")]
    return Outcome(
        index.version,
        sum(not a[c.RETRIEVAL_DOCUMENTS] for a in retrievals),
        sum(int(str(a[c.CONTEXT_TOKENS])) > 0 for a in built),
        sum(not s.status.is_ok for s in chats),
        check(index),
    )


def main() -> None:
    before = run(EMBED_1)
    after = run(EMBEDDERS["wrenholt-embed-2"])
    n = len(QUESTIONS)
    rows = [
        ("index built with", before.index.split(".")[1],
         after.index.split(".")[1]),
        ("questions embedded with", EMBED_1.name, EMBED_1.name),
        ("retrievals with nothing", f"{before.empty} of {n}",
         f"{after.empty} of {n}"),
        ("prompts with a passage", f"{before.with_context} of {n}",
         f"{after.with_context} of {n}"),
        ("model calls failed", before.failed, after.failed),
        ("start-up check", before.check.split(":")[0],
         after.check.split(":")[0]),
    ]  # fmt: skip
    print("FS-08: empty retrieval after a re-index (SIMULATED)")
    print(
        f"{n} policy questions through a retriever without the check"
    )
    print(f"{'':<25}{'before':<19}after re-index")
    for label, a, b in rows:
        print(f"{label:<25}{a!s:<19}{b}")
    print("the check, after the re-index:")
    reason = after.check.split(": ", 1)[1]
    print(textwrap.fill(reason, 68, initial_indent="  ",
                        subsequent_indent="  "))  # fmt: skip
