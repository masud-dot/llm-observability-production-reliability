"""Retrieval telemetry (Chapter 9): versions, IDs, never text."""

import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest

from wrenholt.labs.agent_lab import Telemetry
from wrenholt.labs.fs08_lab import run
from wrenholt.orchestrator.linnet import pack
from wrenholt.rag.corpus import articles, corpus_hash, snapshot
from wrenholt.rag.embed import EMBEDDERS
from wrenholt.rag.index import index_as_of
from wrenholt.rag.retriever import Found, IndexMismatch, Retriever
from wrenholt.telemetry import conventions as c

ROOT = Path(__file__).resolve().parents[2]
E1, E2 = EMBEDDERS["wrenholt-embed-1"], EMBEDDERS["wrenholt-embed-2"]
HASHES = tomllib.loads((ROOT / "data/hashes.toml").read_text())


def test_the_corpus_matches_its_recorded_hashes() -> None:
    recorded = HASHES["corpus"]
    now = snapshot(recorded["as_of"])
    assert len(now) == recorded["count"] == 405
    assert corpus_hash(now) == recorded["sha256_16"]
    stale = snapshot(recorded["stale_as_of"])
    assert corpus_hash(stale) == recorded["stale_sha256_16"]
    assert len(articles()) == 406  # the returns policy has two


def test_a_snapshot_holds_the_version_in_force() -> None:
    def returns(as_of: str) -> str:
        (policy,) = [a for a in snapshot(as_of) if a.id == "HC-0001"]
        return policy.version

    assert returns("2026-02-28") == "returns-2025-09"
    assert returns("2026-03-01") == "returns-2026-03"


def test_a_mismatched_index_is_refused_at_start_up() -> None:
    with pytest.raises(IndexMismatch, match="needs wrenholt-embed-2"):
        Retriever(index_as_of("2026-09-30", E2), E1)


def test_the_retrieval_span_records_versions_not_text() -> None:
    t = Telemetry()
    retriever = Retriever(
        index_as_of("2026-09-30", E1),
        E1,
        tracer_provider=t.tracing,
        meter_provider=t.meters,
    )
    (found, *_) = retriever.search("Can I return this?")
    (span,) = t.named(f"{c.RETRIEVAL} ")
    (embedding,) = t.named(f"{c.EMBEDDINGS} ")
    attrs = dict(span.attributes or {})
    assert span.name == "retrieval help-centre"
    assert embedding.parent is not None
    assert embedding.parent.span_id == span.context.span_id
    assert (embedding.attributes or {})[c.REQUEST_MODEL] == E1.name
    assert attrs[c.INDEX_EMBEDDER] == E1.name
    assert attrs[c.INDEX_VERSION] == retriever.index.version
    documents = cast(
        Sequence[Mapping[str, object]], attrs[c.RETRIEVAL_DOCUMENTS]
    )
    assert dict(documents[0]) == {
        "id": "HC-0001",
        "version": "returns-2026-03",
        "score": found.score,
    }
    assert found.text not in str(attrs)  # the passage stays inside
    assert "return this" not in str(attrs)  # so does the question
    (returned,) = t.points(c.RETURNED)
    assert returned.count == 1


def test_fs08_nothing_fails_and_nothing_is_found() -> None:
    before, after = run(E1), run(E2)
    assert (before.empty, after.empty) == (0, 10)
    assert (before.with_context, after.with_context) == (10, 0)
    assert before.failed == after.failed == 0  # every call "worked"
    assert before.check == "passes"
    assert after.check.startswith("refuses")


@pytest.mark.parametrize(
    ("words", "budget", "kept", "dropped", "used"),
    [
        ((40, 30, 20), 150, 3, 0, 90),
        ((40, 30, 20), 60, 1, 2, 40),  # the second would overflow
        ((40, 30, 20), 39, 0, 3, 0),
    ],
)
def test_the_context_budget(
    words: tuple[int, ...],
    budget: int,
    kept: int,
    dropped: int,
    used: int,
) -> None:
    # Each passage costs its words plus two for its label.
    found = [
        Found(f"HC-{i:04d}", "v", 0.5, " ".join(["w"] * (n - 2)))
        for i, n in enumerate(words)
    ]
    packed = pack(found, budget)
    assert (len(packed.kept), packed.dropped, packed.used) == (
        kept,
        dropped,
        used,
    )
