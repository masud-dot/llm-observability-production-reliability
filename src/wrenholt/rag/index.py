"""The help-centre index (Chapter 9): vectors plus their origin.

An index records the corpus snapshot and the embedder it was built
with, so the version that answered a query, and the embedder its
vectors need, travel with every retrieval.
"""

from dataclasses import dataclass

from wrenholt.rag.corpus import Article, corpus_hash, snapshot
from wrenholt.rag.embed import Embedder, Vector


@dataclass(frozen=True)
class Entry:
    article: Article
    vector: Vector


@dataclass(frozen=True)
class Index:
    version: str  # corpus hash and embedder: what built it
    embedder: str
    entries: tuple[Entry, ...]


def build_index(articles: list[Article], embedder: Embedder) -> Index:
    entries = tuple(
        Entry(a, embedder.embed(f"{a.title}. {a.text}"))
        for a in articles
    )
    version = f"{corpus_hash(articles)[:8]}.{embedder.name}"
    return Index(version, embedder.name, entries)


def index_as_of(as_of: str, embedder: Embedder) -> Index:
    return build_index(snapshot(as_of), embedder)
