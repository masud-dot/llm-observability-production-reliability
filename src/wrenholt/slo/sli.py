"""SLI calculators: count good events and valid events.

Each rule returns True for a good event, False for a bad one and
None for an event the SLI does not count. The rest is counting,
so every result can be checked by hand.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from wrenholt.slo.catalog import SliSpec
from wrenholt.slo.events import RequestEvent

Verdict = bool | None


@dataclass(frozen=True)
class Context:
    """Facts from outside the event, such as the policy in force."""

    policy_in_force: str


@dataclass(frozen=True)
class SliResult:
    sli_id: str
    good: int
    valid: int
    min_events: int

    @property
    def ratio(self) -> float | None:
        """good / valid, or None when there are too few events."""
        if self.valid == 0 or self.valid < self.min_events:
            return None
        return self.good / self.valid


def availability(e: RequestEvent, s: SliSpec, c: Context) -> Verdict:
    if e.outcome in ("client_error", "cancelled"):
        return None
    return e.outcome == "ok"


def latency(e: RequestEvent, s: SliSpec, c: Context) -> Verdict:
    if e.outcome != "ok" or e.ttfc_s is None:
        return None
    return e.ttfc_s <= s.thresholds_s[e.request_class]


def validity(e: RequestEvent, s: SliSpec, c: Context) -> Verdict:
    return e.decision_valid


def groundedness(e: RequestEvent, s: SliSpec, c: Context) -> Verdict:
    return e.grounded


def freshness(e: RequestEvent, s: SliSpec, c: Context) -> Verdict:
    if e.policy_version is None:
        return None
    return e.policy_version == c.policy_in_force


def resolution(e: RequestEvent, s: SliSpec, c: Context) -> Verdict:
    if e.outcome != "ok":
        return None
    return not e.escalated


Rule = Callable[[RequestEvent, SliSpec, Context], Verdict]
RULES: dict[str, Rule] = {
    "availability": availability,
    "latency": latency,
    "validity": validity,
    "groundedness": groundedness,
    "freshness": freshness,
    "resolution": resolution,
}


def measure(
    spec: SliSpec,
    events: Iterable[RequestEvent],
    context: Context,
    min_events: int = 1,
) -> SliResult:
    rule = RULES[spec.kind]
    verdicts = [
        rule(e, spec, context)
        for e in events
        if e.journey in spec.journeys
    ]
    counted = [v for v in verdicts if v is not None]
    return SliResult(spec.id, sum(counted), len(counted), min_events)
