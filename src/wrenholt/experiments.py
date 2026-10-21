"""Experiments (Chapter 18): every failure scenario, run one way.

    uv run --group lab python scripts/experiments.py [FS-03 ...]

Each experiment states its hypothesis before it runs: what must stay
true while the fault is injected (held), or, for a fault no control
absorbs, which signal must show it, measured against the objectives
of Chapter 12 and the paging threshold of Chapter 14 (detected). The
runner runs each scenario's lab in a process of its own, so a
scenario's blast radius is that process and the mocks it starts. It
records the evidence: the command, the value that settles the
hypothesis, the verdict, the time taken and the code version.
"""

import json
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from wrenholt import __version__
from wrenholt.slo.alerts import TIERS
from wrenholt.slo.objectives import load_objectives

ROOT = Path(__file__).resolve().parents[2]
PAGE = float(TIERS[0].burn)  # 14.4: the 1-hour page (Chapter 14)
OBJECTIVE = {
    s.slo: float(s.objective)
    for s in load_objectives().objectives
    if s.objective is not None
}


@dataclass(frozen=True)
class Experiment:
    id: str
    script: str  # scripts/<script>.py
    kind: str  # held, or detected
    hypothesis: str
    pattern: str  # its first group is the evidence
    label: str  # how the evidence reads
    check: Callable[[str], bool]


def _n(v: str) -> float:
    return float(v.replace(",", ""))


E = Experiment
REGISTRY: tuple[Experiment, ...] = (
    E("FS-01", "protect_lab", "held",
      "the retry budget keeps calls per question at 1.05 or under",
      r"  budget\s+[\d,]+\s+([\d.]+)\s", "{} calls a question",
      lambda v: _n(v) <= 1.05),
    E("FS-02", "fs02_fs03_paging", "detected",
      "a two-hour brownout pages within 10 minutes",
      r"FS-02, 2 hours\s+(\d+)", "page after {} min",
      lambda v: _n(v) <= 10),
    E("FS-03", "fallback_lab", "held",
      "with B behind A, no answer fails in a 100 s outage",
      r"fallback B\s+[\d,]+\s+([\d,]+)", "{} answers failed",
      lambda v: _n(v) == 0),
    E("FS-04", "fs04_stream_cut", "detected",
      "a stream cut after its first chunk is recorded as such",
      r"gateway:\s+(stream_interrupted)", "{}", bool),
    E("FS-05", "fs05_malformed_refund", "detected",
      "decision_validity burns at the 1-hour page's rate or more",
      r"decision_validity\s+30 of 30\s+0 of 30\s+(\d+)",
      "burn rate {}", lambda v: _n(v) >= PAGE),
    E("FS-06", "fs06_tool_loop", "held",
      "the repeat check stops a tool loop after one lookup",
      r"tool calls\s+\d+\s+(\d+)", "{} tool call",
      lambda v: _n(v) <= 1),
    E("FS-07", "fs07_duplicate_refund", "held",
      "a key per refund pays a timed-out refund once",
      r"refunds made\s+\d+\s+(\d+)", "{} refund made",
      lambda v: _n(v) == 1),
    E("FS-08", "fs08_empty_retrieval", "held",
      "start-up refuses an index built by another embedder",
      r"start-up check\s+passes\s+(\w+)", "start-up {}",
      lambda v: v == "refuses"),
    E("FS-09", "fs09_sli_report", "detected",
      "policy_freshness falls below its objective",
      r"policy_freshness\s+L3\s+\S+\s+\S+\s+\S+\s+([\d.]+)%",
      "freshness {}%",
      lambda v: _n(v) / 100 < OBJECTIVE["policy_freshness"]),
    E("FS-10", "fs10_prompt_regression", "detected",
      "evaluation flags a refusing prompt within 4 hours",
      r"full rollout, 10% evaluated: flagged after (\d+) hours",
      "flagged after {} h", lambda v: _n(v) <= 4),
    E("FS-11", "fs11_model_change", "detected",
      "a response from an unpinned model is a mismatch",
      r"model_mismatch\s+False\s+(\w+)", "mismatch {}",
      lambda v: v == "True"),
    E("FS-12", "fs12_token_explosion", "detected",
      "the output-token p99 more than doubles in the histogram",
      r"output tokens, p99 \(histogram\)\s+[\d.]+\s+([\d.]+)",
      "p99 {} tokens", lambda v: _n(v) > 2 * 59.7),
    E("FS-13", "fallback_lab", "held",
      "start-up refuses a fallback the peak cannot afford",
      r"mock-a-large\s+5 x price: \$[\d.]+ an hour, (refused)",
      "mock-a-large {}", lambda v: v == "refused"),
    E("FS-14", "fs14_pii", "held",
      "as designed, exported telemetry holds no personal data",
      r"as designed, vault\s+(\d+\s+\d+\s+\d+\s+\d+)", "found {}",
      lambda v: set(v.split()) == {"0"}),
    E("FS-15", "fs15_sampling_blind_spot", "held",
      "sampling keeps every substituted-model trace",
      r"substituted model\s+\d+\s+\d+ of \d+\s+(\d+ of \d+)",
      "kept {}", lambda v: v.split(" of ")[0] == v.split(" of ")[1]),
    E("FS-16", "fallback_lab", "held",
      "at twice the peak, admitted answers keep p95 within 2.5 s",
      r"admission\s+[\d,]+\s+([\d.]+)", "p95 {} s",
      lambda v: _n(v) <= 2.5),
    E("FS-17", "fs17_over_blocking", "detected",
      "not_refused burns at the 1-hour page's rate or more",
      r"not_refused\s+120 of 120\s+90 of 120\s+(\d+)",
      "burn rate {}", lambda v: _n(v) >= PAGE),
    E("FS-18", "protect_lab", "held",
      "a spent quota is never retried",
      r"FS-18 quota\s+(\S+)", "{}", lambda v: v == "not_retryable"),
)  # fmt: skip
VERDICTS = {
    ("held", True): "held",
    ("held", False): "BROKEN",
    ("detected", True): "detected",
    ("detected", False): "MISSED",
}


@dataclass(frozen=True)
class Result:
    id: str
    kind: str
    hypothesis: str
    command: str
    evidence: str
    verdict: str
    seconds: float


def judge(e: Experiment, output: str, seconds: float) -> Result:
    found = re.search(e.pattern, output)
    value = " ".join(found.group(1).split()) if found else ""
    ok = bool(found) and e.check(value)
    return Result(
        e.id,
        e.kind,
        e.hypothesis,
        f"python scripts/{e.script}.py",
        e.label.format(value) if found else "no evidence",
        VERDICTS[(e.kind, ok)],
        round(seconds, 1),
    )


def run(ids: Sequence[str] = ()) -> list[Result]:
    """Each script once, whichever experiments share it."""
    chosen = [e for e in REGISTRY if not ids or e.id in ids]
    outputs: dict[str, tuple[str, float]] = {}
    for script in dict.fromkeys(e.script for e in chosen):
        start = time.monotonic()
        done = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / f"{script}.py")],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=ROOT,
            check=False,
        )
        outputs[script] = (done.stdout, time.monotonic() - start)
    return [judge(e, *outputs[e.script]) for e in chosen]


def report(results: Sequence[Result]) -> list[str]:
    lines = [f"experiments, wrenholt {__version__} (SIMULATED)"]
    for r in results:
        what = f"{r.id:<7}{r.verdict:<10}{r.evidence:<38}"
        lines.append(f"{what}{r.seconds:>5.1f} s")
    broken = sum(r.verdict in ("BROKEN", "MISSED") for r in results)
    lines.append(f"{len(results)} run, {broken} hypotheses failed")
    return lines


def record(results: Sequence[Result], path: Path) -> None:
    body = {
        "version": __version__,
        "label": "SIMULATED",
        "results": [asdict(r) for r in results],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=1) + "\n")


def main(argv: Sequence[str] = ()) -> int:
    results = run(argv)
    print("\n".join(report(results)))
    record(results, ROOT / "experiments" / "latest.json")
    failed = {"BROKEN", "MISSED"}
    return 1 if any(r.verdict in failed for r in results) else 0
