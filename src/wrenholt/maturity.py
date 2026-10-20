"""A reliability self-assessment (Chapter 20).

One question for each stage of the spine, answered from the
repository rather than from memory. A stage counts only when the
stages before it count: an answer cannot be evaluated before it is
measured, nor improved before it is recovered.
"""

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from wrenholt.gates import Spend, budget_gate, gates
from wrenholt.slo.alerts import RUNBOOKS
from wrenholt.slo.objectives import load_objectives

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ".github/workflows/gates.yml"
POLICY = "docs/error_budget_policy.md"
OK = {"held", "detected"}


@dataclass(frozen=True)
class Answer:
    stage: str
    evidence: str
    met: bool


def assess(root: Path = ROOT) -> list[Answer]:
    owned = [s for s in load_objectives().objectives if s.owner]
    runbook = (root / RUNBOOKS).read_text()
    linked = [s for s in owned if f"\n## {s.slo}\n" in runbook]
    latest = root / "experiments/latest.json"
    record = json.loads(latest.read_text())
    held = [r for r in record["results"] if r["verdict"] in OK]
    workflow = (root / WORKFLOW).read_text()
    emits = "drift" in gates(["src/wrenholt/gateway/client.py"])
    says = (
        "src/wrenholt/orchestrator/prompts.py",
        "src/wrenholt/gateway/prices.yaml",
        "src/wrenholt/rag/index.py",
    )
    spent = [Spend("x", "team", Decimal(0))]
    frozen = not budget_gate(spent, "team", set()).passed
    return [
        Answer("Observe", "drift gate on every code change",
               emits and "gates.py ci" in workflow),
        Answer("Measure", f"{len(owned)} objectives, each owned",
               bool(owned) and (root / POLICY).exists()),
        Answer("Evaluate", "evaluation gate on prompt, model, index",
               all("evaluation" in gates([p]) for p in says)),
        Answer("Diagnose",
               f"{len(linked)} of {len(owned)} pages have a runbook",
               len(linked) == len(owned)),
        Answer("Recover",
               f"{len(held)} of {len(record['results'])} "
               "experiments held or detected",
               len(held) == len(record["results"])),
        Answer("Improve", "the budget policy holds releases",
               frozen),
    ]  # fmt: skip


def level(answers: list[Answer]) -> int:
    """Stages met in spine order, up to the first one missed."""
    n = 0
    for a in answers:
        if not a.met:
            break
        n += 1
    return n


def main() -> int:
    answers = assess()
    print("Reliability self-assessment (from the repository)")
    for a in answers:
        met = "yes" if a.met else "no"
        print(f"  {a.stage:<10}{a.evidence:<44}{met}")
    print(f"  level {level(answers)} of {len(answers)}")
    return 0
