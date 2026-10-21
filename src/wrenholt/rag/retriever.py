"""Retrieval with its own telemetry (Chapter 9).

Each search is a retrieval span with an embeddings span beneath
it. The spans record which index answered and which embedder made
the query's vector, plus the IDs, versions and scores of what came
back: never the query, never a passage. A retriever refuses an
index whose vectors another embedder made.
"""

import time
from dataclasses import dataclass

from opentelemetry import metrics, trace
from opentelemetry.trace import SpanKind

from wrenholt.rag.embed import Embedder, Vector, similarity
from wrenholt.rag.index import Index
from wrenholt.telemetry import conventions as c

SOURCE = "help-centre"  # gen_ai.data_source.id


class IndexMismatch(Exception):
    """The index's vectors came from another embedder (FS-08)."""


@dataclass(frozen=True)
class Found:
    id: str
    version: str
    score: float
    text: str  # in process only: never exported


class Retriever:
    def __init__(
        self,
        index: Index,
        embedder: Embedder,
        *,
        top_k: int = 3,
        min_score: float = 0.2,
        tracer_provider: trace.TracerProvider | None = None,
        meter_provider: metrics.MeterProvider | None = None,
    ) -> None:
        self._check(index, embedder)
        self.index, self._embedder = index, embedder
        self._k, self._min = top_k, min_score
        self._tracer = trace.get_tracer(
            "wrenholt.rag", tracer_provider=tracer_provider
        )
        meter = metrics.get_meter(
            "wrenholt.rag", meter_provider=meter_provider
        )
        self._duration = meter.create_histogram(
            c.OPERATION_DURATION,
            unit="s",
            description="GenAI operation duration.",
            explicit_bucket_boundaries_advisory=c.DURATION_BUCKETS,
        )
        self._returned = meter.create_histogram(
            c.RETURNED,
            unit="{document}",
            description="Documents returned per retrieval.",
            explicit_bucket_boundaries_advisory=c.RETURNED_BUCKETS,
        )

    @staticmethod
    def _check(index: Index, embedder: Embedder) -> None:
        """The start-up check. Equal dimensions prove nothing: the
        vectors must come from the same embedder."""
        if index.embedder != embedder.name:
            raise IndexMismatch(
                f"index {index.version} needs {index.embedder}; "
                f"queries use {embedder.name}"
            )

    def search(self, query: str) -> list[Found]:
        attrs = {
            c.OPERATION_NAME: c.RETRIEVAL,
            c.DATA_SOURCE_ID: SOURCE,
            c.RETRIEVAL_TOP_K: self._k,
            c.INDEX_VERSION: self.index.version,
            c.INDEX_EMBEDDER: self.index.embedder,
        }
        start = time.perf_counter()
        with self._tracer.start_as_current_span(
            f"{c.RETRIEVAL} {SOURCE}",
            kind=SpanKind.CLIENT,
            attributes=attrs,
        ) as span:
            query_vector = self._embed(query)
            ranked = sorted(
                (
                    (similarity(query_vector, e.vector), e.article)
                    for e in self.index.entries
                ),
                key=lambda pair: -pair[0],
            )
            found = [
                Found(a.id, a.version, round(score, 3), a.text)
                for score, a in ranked[: self._k]
                if score >= self._min
            ]
            documents = [  # opt-in: IDs, versions, scores; no text
                {"id": f.id, "version": f.version, "score": f.score}
                for f in found
            ]
            span.set_attribute(c.RETRIEVAL_DOCUMENTS, documents)
        where = {
            c.DATA_SOURCE_ID: SOURCE,
            c.INDEX_VERSION: self.index.version,
        }
        self._returned.record(len(found), where)
        took = time.perf_counter() - start
        self._duration.record(took, {c.OPERATION_NAME: c.RETRIEVAL})
        return found

    def _embed(self, text: str) -> Vector:
        model = self._embedder
        attrs = {
            c.OPERATION_NAME: c.EMBEDDINGS,
            c.PROVIDER_NAME: model.provider,
            c.REQUEST_MODEL: model.name,
        }
        start = time.perf_counter()
        with self._tracer.start_as_current_span(
            f"{c.EMBEDDINGS} {model.name}",
            kind=SpanKind.CLIENT,
            attributes={
                **attrs,
                c.EMBEDDING_DIMENSIONS: model.dimensions,
            },
        ):
            vector = model.embed(text)
        self._duration.record(time.perf_counter() - start, attrs)
        return vector
