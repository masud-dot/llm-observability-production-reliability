"""Cost per resolved ticket, and where an answer's time goes
(Chapter 11).

A ticket is one customer conversation; Linnet's are one answer
long. Its cost is every model call made for it, a failed or an
escalated answer's included, but only resolved tickets divide the
total. So a failure, an escalation, a retry or a fallback raises
the cost per resolved ticket even when no price has changed.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from opentelemetry.sdk.trace import ReadableSpan

from wrenholt.slo.events import RequestEvent
from wrenholt.telemetry import conventions as c


@dataclass(frozen=True)
class Ticket:
    journey: str
    cost: Decimal
    resolved: bool


def resolved(event: RequestEvent) -> bool:
    """The resolution SLI's good event: answered, and no human
    agent needed (the SLI catalogue, Chapter 2)."""
    return event.outcome == "ok" and not event.escalated


def tickets(
    events: Iterable[RequestEvent], cost: Mapping[str, Decimal]
) -> list[Ticket]:
    """Each conversation, at its journey's measured cost."""
    return [
        Ticket(e.journey, cost[e.journey], resolved(e))
        for e in events
    ]


def cost_per_resolved(found: Sequence[Ticket]) -> Decimal:
    done = sum(t.resolved for t in found)
    if done == 0:
        raise ValueError("no resolved tickets")
    return sum((t.cost for t in found), Decimal(0)) / done


PARTS = (
    "queueing", "retrieval", "tools", "model", "first_chunk",
    "generation", "other",
)  # fmt: skip


@dataclass(frozen=True)
class Timed:
    """One direct child of an answer's agent span, in seconds."""

    kind: str  # retrieval, tool or chat; anything else is other
    seconds: float
    waited: float = 0.0  # a chat's retry delays, before attempts
    first_chunk: float | None = None  # a streamed chat's wait


def decompose(
    total: float, parts: Iterable[Timed]
) -> dict[str, float]:
    """An answer's time by part. Queueing is the gateway's waiting
    between attempts; time to first chunk counts from the first
    attempt; what no child explains is other."""
    found = dict.fromkeys(PARTS, 0.0)
    for part in parts:
        if part.kind == "retrieval":
            found["retrieval"] += part.seconds
        elif part.kind == "tool":
            found["tools"] += part.seconds
        elif part.kind == "chat":
            found["queueing"] += part.waited
            if part.first_chunk is None:
                found["model"] += part.seconds - part.waited
            else:
                first = part.first_chunk - part.waited
                found["first_chunk"] += first
                found["generation"] += part.seconds - part.first_chunk
    found["other"] = total - sum(found.values())
    return found


def _seconds(span: ReadableSpan) -> float:
    return ((span.end_time or 0) - (span.start_time or 0)) / 1e9


def from_spans(spans: Sequence[ReadableSpan]) -> dict[str, float]:
    """decompose() over one answer's finished spans."""
    (agent,) = [s for s in spans if s.name.startswith(c.INVOKE_AGENT)]
    root = agent.context.span_id if agent.context else None
    kinds = {c.RETRIEVAL: "retrieval", c.EXECUTE_TOOL: "tool"}
    kinds[c.CHAT] = "chat"
    parts = []
    for span in spans:
        if span.parent is None or span.parent.span_id != root:
            continue
        kind = kinds.get(span.name.split(" ")[0], "other")
        own = span.context.span_id if span.context else None
        waited = sum(
            float((a.attributes or {}).get(c.ATTEMPT_DELAY, 0.0))
            for a in spans
            if a.parent is not None and a.parent.span_id == own
        )
        attrs = span.attributes or {}
        first = attrs.get(c.RESPONSE_TIME_TO_FIRST_CHUNK)
        parts.append(
            Timed(
                kind,
                _seconds(span),
                waited,
                None if first is None else float(str(first)),
            )
        )
    return decompose(_seconds(agent), parts)


def histogram_quantile(
    q: float, bounds: Sequence[float], counts: Sequence[int]
) -> float:
    """What PromQL's histogram_quantile() returns for one classic
    histogram: counts per bucket, the last for +Inf. The rank's
    bucket is found, then the value interpolated linearly inside
    it; a rank in the +Inf bucket gives the highest bound."""
    rank = q * sum(counts)
    seen = 0
    for i, count in enumerate(counts):
        if count and seen + count >= rank:
            if i == len(bounds):
                return float(bounds[-1])
            low = bounds[i - 1] if i else 0.0
            share = (rank - seen) / count
            return low + (bounds[i] - low) * share
        seen += count
    return float("nan")


def bucket_counts(
    values: Iterable[int], bounds: Sequence[float]
) -> list[int]:
    """Values per bucket, as the SDK counts them: a bucket holds
    values up to and including its bound."""
    counts = [0] * (len(bounds) + 1)
    for value in values:
        i = next(
            (i for i, b in enumerate(bounds) if value <= b),
            len(bounds),
        )
        counts[i] += 1
    return counts
