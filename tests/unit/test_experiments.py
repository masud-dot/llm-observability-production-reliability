"""Experiments (Chapter 18): the load generator, the breaking-point
lab and the runner."""

import asyncio
import json
from pathlib import Path

import pytest

from wrenholt import experiments as x
from wrenholt.labs import breaking_lab as lab
from wrenholt.load import drive, gradual, impulse


def test_a_pattern_always_gives_the_same_arrivals() -> None:
    ramp = gradual(0, 120, 120)
    assert ramp == gradual(0, 120, 120)
    assert len(ramp) == 7200  # the area under the ramp
    spike = impulse(30, 120, at=40, width=10, seconds=120)
    assert len(spike) == 30 * 110 + 120 * 10
    inside = [t for t in spike if 40 <= t < 50]
    assert abs(len(inside) - 1200) <= 1  # one may round onto 50.0


def test_drive_starts_each_call_on_time_without_waiting() -> None:
    async def call(i: int) -> int:
        await asyncio.sleep(0.2)
        if i == 3:
            raise ValueError("refused")
        return i

    times = [i * 0.005 for i in range(10)]
    shots = asyncio.run(drive(times, call))
    assert [s.index for s in shots] == list(range(10))
    assert max(s.start for s in shots) < min(s.end for s in shots)
    assert isinstance(shots[3].result, ValueError)
    assert [s.result for s in shots if s.index != 3] == [
        0, 1, 2, 4, 5, 6, 7, 8, 9
    ]  # fmt: skip


def test_the_breaking_point_and_past_it() -> None:
    queue, admission = lab.ramp(False), lab.ramp(True)
    assert [w.p95_s for w in queue] == [
        2.0,
        2.0,
        4.23,
        10.0,
        10.0,
        10.0,
    ]
    assert [w.failed for w in queue] == [0, 0, 0, 252, 900, 1300]
    assert {w.failed for w in admission} == {0}
    assert {w.p95_s for w in admission} == {2.0}
    assert [w.full for w in admission][2:] == [720, 719, 720, 724]
    q, a = lab.spike(False), lab.spike(True)
    assert (sum(w.failed for w in q), lab.recovered(q)) == (390, 75)
    assert (sum(w.failed for w in a), lab.recovered(a)) == (0, 50)
    assert sum(w.degraded for w in a) == 840
    assert max(len(line) for line in lab.report()) <= 70


def test_the_registry_covers_every_scenario() -> None:
    ids = [e.id for e in x.REGISTRY]
    assert ids == [f"FS-{n:02d}" for n in range(1, 19)]
    assert x.PAGE == 14.4 and x.OBJECTIVE["policy_freshness"] == 0.99


@pytest.mark.parametrize(
    ("output", "verdict", "evidence"),
    [
        (
            "  FS-18 quota          not_retryable\n",
            "held",
            "not_retryable",
        ),
        ("  FS-18 quota          retry in 1 s\n", "BROKEN", "retry"),
        ("nothing to see\n", "BROKEN", "no evidence"),
    ],
)
def test_a_held_hypothesis_is_judged_on_its_evidence(
    output: str, verdict: str, evidence: str
) -> None:
    fs18 = x.REGISTRY[17]
    r = x.judge(fs18, output, 1.0)
    assert (r.verdict, r.evidence) == (verdict, evidence)


def test_a_detection_is_judged_against_the_objectives() -> None:
    fs09 = x.REGISTRY[8]
    row = "policy_freshness  L3  90/90 100.0%  54/90  {}%  8/8  n/a\n"
    assert x.judge(fs09, row.format("60.0"), 0).verdict == "detected"
    assert x.judge(fs09, row.format("99.5"), 0).verdict == "MISSED"


def test_the_runner_runs_scripts_and_records_the_evidence(
    tmp_path: Path,
) -> None:
    results = x.run(["FS-09", "FS-11", "FS-18"])
    assert [(r.id, r.verdict) for r in results] == [
        ("FS-09", "detected"),
        ("FS-11", "detected"),
        ("FS-18", "held"),
    ]
    x.record(results, tmp_path / "latest.json")
    body = json.loads((tmp_path / "latest.json").read_text())
    assert body["label"] == "SIMULATED" and len(body["results"]) == 3
    assert max(len(line) for line in x.report(results)) <= 70
