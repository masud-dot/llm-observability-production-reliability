"""FS-09: availability passes while customers get stale answers."""

from wrenholt.slo.catalog import load_catalog
from wrenholt.slo.fs09 import fs09_hour, measure_all, normal_hour

CATALOG = load_catalog()


def ratios(events_hour: str) -> dict[str, float | None]:
    events = normal_hour() if events_hour == "normal" else fs09_hour()
    results = measure_all(CATALOG, events)
    return {r.sli_id: r.ratio for r in results}


def test_fs09_is_invisible_to_availability_and_latency() -> None:
    normal, stale = ratios("normal"), ratios("fs09")
    for sli in ("availability", "ttfc", "decision_validity"):
        assert normal[sli] == stale[sli] == 1.0


def test_grounding_checks_pass_on_stale_context() -> None:
    # The evaluator compares each answer with what retrieval gave
    # it. Stale policy text still grounds the answer.
    assert ratios("fs09")["groundedness"] == 1.0


def test_freshness_and_resolution_show_the_failure() -> None:
    normal, stale = ratios("normal"), ratios("fs09")
    # 24 of 60 policy answers and 12 of 30 refund answers relied
    # on the superseded policy: (90 - 36) / 90 = 0.6.
    assert normal["policy_freshness"] == 1.0
    assert stale["policy_freshness"] == 54 / 90 == 0.6
    # Escalations rose from 6 to 24 of 120 conversations.
    assert normal["resolution"] == 114 / 120 == 0.95
    assert stale["resolution"] == 96 / 120 == 0.8
