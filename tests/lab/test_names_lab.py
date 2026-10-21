"""Chapter 5 lab: the pinned specification against the packages.

When a package release catches up with the specification, these
tests fail, and Chapter 5 and Appendix B need revising.
"""

from wrenholt.labs.names_lab import emitted, package
from wrenholt.telemetry import drift

OLD_PROVIDER, NEW_PROVIDER = "gen_ai.system", "gen_ai.provider.name"
OLD_TOKENS = "gen_ai.client.token.usage"


def test_the_specification_dropped_the_old_names() -> None:
    snap = drift.load_snapshot()
    assert OLD_PROVIDER not in snap["attributes"]
    assert OLD_TOKENS not in snap["metrics"]
    assert (
        "gen_ai.client.inference.usage.input_tokens"
        in snap["metrics"]
    )


def test_the_pinned_package_still_ships_them() -> None:
    attrs, metrics = package()
    assert OLD_PROVIDER in attrs
    assert OLD_TOKENS in metrics
    assert not any(".inference.usage." in m for m in metrics)


def test_the_opt_in_moves_the_provider_name_but_not_tokens() -> None:
    unset = emitted(None)
    latest = emitted("gen_ai_latest_experimental")
    assert OLD_PROVIDER in unset["attributes"]
    assert NEW_PROVIDER in latest["attributes"]
    assert NEW_PROVIDER not in unset["attributes"]
    assert OLD_TOKENS in unset["metrics"]
    assert OLD_TOKENS in latest["metrics"]
    assert "gen_ai.token.type" in unset["metric_attributes"]
    assert "gen_ai.token.type" in latest["metric_attributes"]
