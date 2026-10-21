"""Event names against the pinned GenAI conventions (Chapter 13)."""

from wrenholt.telemetry import conventions as c
from wrenholt.telemetry import drift


def test_the_evaluation_event_is_in_the_pinned_conventions() -> None:
    snapshot = drift.load_snapshot()
    assert drift.events_against_snapshot(c.EVENTS, snapshot) == []
    renamed = [c.Name("gen_ai.evaluation.outcome", "event", "genai")]
    assert drift.events_against_snapshot(renamed, snapshot)
