"""The rename drill: a silent dashboard break the checks catch."""

from wrenholt.labs.rename_drill import drill
from wrenholt.telemetry import conventions as c


def test_the_drill_breaks_silently_and_the_checks_catch_it() -> None:
    pinned, renamed = drill(False), drill(True)
    assert (pinned.missing, pinned.problems) == ([], [])
    assert renamed.missing == ["gen_ai_provider_name"]
    assert renamed.problems[0].startswith("gen_ai.system: not in")
    panels = renamed.problems[1:]  # one per panel grouping by it
    assert panels
    assert all("label gen_ai_provider_name" in p for p in panels)
    assert c.PROVIDER_NAME == "gen_ai.provider.name"  # restored
