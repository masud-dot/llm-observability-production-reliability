"""Degraded answers (Chapter 17): what Linnet says without a model.

The ladder's lower rungs make no model call. A question whose best
passage has a brief, written by the help-centre team for the
version in force, gets the brief; otherwise the passage itself. A
refund, a question with no passage or a passage no longer in force
goes to a person: Linnet never answers from a model's memory, and
never makes a refund without one.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from opentelemetry import trace

from wrenholt.gateway.fallback import Mode, mark
from wrenholt.rag.retriever import Found


@dataclass(frozen=True)
class Brief:
    version: str  # the article version it was written for
    text: str


# The help-centre team's briefs for its most-asked articles
# (SYNTHETIC, from Chapter 2's corpus).
BRIEFS: Final = {
    "HC-0001": Brief(
        "returns-2026-03",
        "Most items can be returned within 30 days of delivery."
        " Start a return from My orders and we email a prepaid"
        " label.",
    ),
    "HC-0002": Brief(
        "refund-timing-2025-11",
        "Refunds reach your card within five working days of your"
        " return reaching our warehouse.",
    ),
}
HANDOFF: Final = "A member of our team will reply to you here soon."


@dataclass(frozen=True)
class Degraded:
    mode: Mode
    text: str


def degrade(
    found: Sequence[Found],
    request_class: str,
    in_force: Mapping[str, str],
    reason: str,
    briefs: Mapping[str, Brief] = BRIEFS,
) -> Degraded:
    """The best answer without a model, recorded on the span."""
    top = found[0] if found else None
    if (
        request_class == "critical_action"
        or top is None
        or in_force.get(top.id) != top.version
    ):
        out = Degraded(Mode.HANDOFF, HANDOFF)
    elif (
        brief := briefs.get(top.id)
    ) and brief.version == top.version:
        out = Degraded(Mode.CACHED, brief.text)
    else:
        out = Degraded(
            Mode.CITATION, f"From our help centre: {top.text}"
        )
    mark(trace.get_current_span(), out.mode, reason)
    return out
