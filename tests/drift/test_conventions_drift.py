"""Drift suite: emitted names, the module and the pinned snapshot."""

import importlib.util
import os
from pathlib import Path

import pytest

from wrenholt.telemetry import conventions as c
from wrenholt.telemetry import drift

ROOT = Path(__file__).resolve().parents[2]
Emitted = tuple[set[str], list[tuple[str, str, str, set[str]]]]


def test_registry_matches_the_pinned_snapshot() -> None:
    snapshot = drift.load_snapshot()
    assert snapshot["commit"] == c.GENAI_COMMIT
    assert drift.against_snapshot(c.REGISTRY, snapshot) == []


def test_core_names_are_stable_in_the_pinned_package() -> None:
    assert drift.against_core(c.REGISTRY) == []


def test_gateway_emits_only_registered_names(
    emitted: Emitted,
) -> None:
    attrs, metrics = emitted
    names = {m[0] for m in metrics}
    assert drift.against_emitted(c.REGISTRY, attrs, names) == []


def test_emitted_metrics_have_their_registered_shape(
    emitted: Emitted,
) -> None:
    shapes = {(n.name, n.instrument, n.unit) for n in c.REGISTRY}
    assert {(m[0], m[1], m[2]) for m in emitted[1]} <= shapes


def test_every_registered_name_is_emitted(emitted: Emitted) -> None:
    attrs, metrics = emitted
    seen = attrs | {m[0] for m in metrics}
    assert {n.name for n in c.REGISTRY} <= seen  # no dead entries


def test_content_exists_upstream_and_is_never_emitted(
    emitted: Emitted,
) -> None:
    assert set(c.CONTENT) <= set(drift.load_snapshot()["attributes"])
    assert not set(c.CONTENT) & emitted[0]


CHECKOUT = os.environ.get("SEMCONV_GENAI_DIR")


@pytest.mark.skipif(not CHECKOUT, reason="SEMCONV_GENAI_DIR not set")
def test_snapshot_equals_the_pinned_checkout() -> None:
    script = ROOT / "scripts" / "semconv_snapshot.py"
    spec = importlib.util.spec_from_file_location("snap", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (
        module.snapshot(Path(str(CHECKOUT))) == drift.load_snapshot()
    )


def test_the_pin_is_the_same_everywhere() -> None:
    workflow = ROOT / ".github" / "workflows" / "compose-smoke.yml"
    assert c.GENAI_COMMIT in workflow.read_text()
    assert c.GENAI_COMMIT in (ROOT / "versions.toml").read_text()
