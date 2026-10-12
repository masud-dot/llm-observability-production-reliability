"""FS-09 stale return policy as SLI evidence (SIMULATED).

Three hours of Linnet traffic, built deterministically: a normal
sale-day hour, an hour in which the policy index serves the
superseded returns policy to some answers, and a quiet night
hour. Chapter 9 replays FS-09 against the live retriever: the
policy version comes from each retrieval span's documents.
"""

from collections.abc import Mapping, Sequence

from wrenholt.slo.catalog import Catalog
from wrenholt.slo.events import RequestEvent
from wrenholt.slo.sli import Context, SliResult, measure

IN_FORCE = "returns-2026-03"
SUPERSEDED = "returns-2025-09"
CONTEXT = Context(policy_in_force=IN_FORCE)


def policy_answers(
    n: int, stale: int = 0, escalated: int = 0
) -> list[RequestEvent]:
    return [
        RequestEvent(
            journey="policy_question",
            request_class="interactive",
            outcome="ok",
            ttfc_s=1.2,
            policy_version=SUPERSEDED if i < stale else IN_FORCE,
            grounded=True,
            escalated=i < escalated,
        )
        for i in range(n)
    ]


def order_answers(
    n: int, escalated: int = 0, failed: int = 0
) -> list[RequestEvent]:
    return [
        RequestEvent(
            journey="order_status",
            request_class="interactive",
            outcome="server_error" if i < failed else "ok",
            ttfc_s=None if i < failed else 0.9,
            escalated=i < escalated,
        )
        for i in range(n)
    ]


def refund_answers(
    n: int, stale: int = 0, escalated: int = 0
) -> list[RequestEvent]:
    return [
        RequestEvent(
            journey="refund_request",
            request_class="critical_action",
            outcome="ok",
            ttfc_s=2.8,
            policy_version=SUPERSEDED if i < stale else IN_FORCE,
            decision_valid=True,
            escalated=i < escalated,
        )
        for i in range(n)
    ]


def normal_hour() -> list[RequestEvent]:
    return (
        policy_answers(60, escalated=3)
        + order_answers(30, escalated=1)
        + refund_answers(30, escalated=2)
    )


def fs09_hour() -> list[RequestEvent]:
    return (
        policy_answers(60, stale=24, escalated=14)
        + order_answers(30, escalated=2)
        + refund_answers(30, stale=12, escalated=8)
    )


def night_hour() -> list[RequestEvent]:
    return (
        policy_answers(6)
        + order_answers(4, failed=1)
        + refund_answers(2)
    )


def measure_all(
    catalog: Catalog, events: list[RequestEvent]
) -> list[SliResult]:
    return [
        measure(spec, events, CONTEXT, catalog.min_events)
        for spec in catalog.slis
    ]


def cell(result: SliResult) -> str:
    counts = f"{result.good}/{result.valid}"
    if result.ratio is None:
        return f"{counts}    n/a"
    return f"{counts} {result.ratio:6.1%}"


def report(catalog: Catalog) -> str:
    hours = [normal_hour(), fs09_hour(), night_hour()]
    columns = [measure_all(catalog, h) for h in hours]
    lines = [
        "FS-09 stale return policy (SIMULATED): candidate SLIs",
        f"{'sli':<18}{'layer':<6}{'normal':>15}{'FS-09':>15}"
        f"{'night':>15}",
    ]
    for i, spec in enumerate(catalog.slis):
        cells = "".join(f"{cell(col[i]):>15}" for col in columns)
        lines.append(f"{spec.id:<18}{spec.layer:<6}{cells}")
    return "\n".join(lines)


def policy_version(
    documents: Sequence[Mapping[str, object]],
) -> str | None:
    """The returns-policy version one retrieval returned, read from
    its span's gen_ai.retrieval.documents (Chapter 9), or None when
    the answer relied on no policy document."""
    for document in documents:
        version = str(document.get("version", ""))
        if version.startswith("returns-"):
            return version
    return None
