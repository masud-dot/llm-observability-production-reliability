"""Release gates and canary analysis (Chapter 20).

A change is classified by the paths it touches, and each change
type has gates to pass. CI runs the contract, drift and evaluation
gates on the pull request; the deploy pipeline runs the error-budget
gate and then the canary. A gate blocks on evidence of harm; passing
one means only that no harm showed at the size of its evidence.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from fnmatch import fnmatch

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import StatusCode

from wrenholt.evaluation.drift import Rate, rate_shift
from wrenholt.slo.objectives import load_objectives
from wrenholt.telemetry import conventions as c

# The paths that make a change each type. A path can make more than
# one: app.py holds the model pins as well as code.
KINDS: Mapping[str, tuple[str, ...]] = {
    "prompt": ("src/wrenholt/orchestrator/prompts.py",),
    "model": (
        "src/wrenholt/api/app.py",
        "src/wrenholt/gateway/prices.yaml",
    ),
    "index": ("src/wrenholt/rag/*",),
    "configuration": (
        "deploy/*",
        "docker-compose*.yml",
        ".github/*",
        "src/wrenholt/slo/*.yaml",
        "versions.toml",
        "uv.lock",
    ),
    "code": ("src/*.py", "services/*", "tests/*", "pyproject.toml"),
}
# What each type can break: what Linnet says, or what we emit.
CI: Mapping[str, tuple[str, ...]] = {
    "prompt": ("evaluation",),
    "model": ("evaluation",),
    "index": ("evaluation",),
    "configuration": ("contract", "drift"),
    "code": ("contract", "drift"),
}
ORDER = ("contract", "drift", "evaluation")
PYTHON = sys.executable
COMMANDS: Mapping[str, tuple[str, ...]] = {
    "contract": (
        PYTHON, "-m", "pytest", "-q",
        "tests/unit/test_gateway_contract.py",
        "tests/unit/test_pipeline_config.py",
        "tests/privacy",
    ),
    "drift": (
        PYTHON, "-m", "pytest", "-q",
        "tests/drift", "tests/unit/test_cardinality.py",
    ),
    "evaluation": (PYTHON, "scripts/gates.py", "evaluate"),
}  # fmt: skip


def kinds(paths: Iterable[str]) -> set[str]:
    """The change types a set of changed paths makes."""
    return {
        kind
        for path in paths
        for kind, globs in KINDS.items()
        if any(fnmatch(path, g) for g in globs)
    }


def gates(paths: Iterable[str]) -> list[str]:
    """The CI gates a change must pass, in a fixed order."""
    wanted = {g for k in kinds(paths) for g in CI[k]}
    return [g for g in ORDER if g in wanted]


def budget(slo: str) -> float:
    """The share of events an objective lets fail."""
    (s,) = [s for s in load_objectives().objectives if s.slo == slo]
    return float(s.budget)


@dataclass(frozen=True)
class Verdict:
    gate: str
    passed: bool
    reason: str


def evaluation(
    refused: Mapping[str, bool],
    mix: Mapping[str, int],
    allowed: float,
) -> Verdict:
    """Block a candidate whose refused cases would carry more of an
    hour's traffic than the not_refused objective lets fail."""
    cases = sorted(j for j, r in refused.items() if r)
    share = sum(mix[j] for j in cases) / sum(mix.values())
    said = f"{share:.1%} of the mix refused, budget {allowed:.1%}"
    if share > allowed:
        named = ", ".join(cases)
        return Verdict("evaluation", False, f"{said}: {named}")
    return Verdict("evaluation", True, said)


@dataclass(frozen=True)
class Spend:
    slo: str
    owner: str
    left: Decimal  # share of the window's budget left
    outside: bool = False  # spent by a cause the owner can't control


EXEMPT = {"fix", "security"}  # labels the policy lets through


def budget_gate(
    spends: Iterable[Spend], team: str, labels: set[str]
) -> Verdict:
    """docs/error_budget_policy.md as code: an owner whose budget is
    exhausted ships only fixes for the cause and security fixes;
    other teams carry on; an outside cause freezes nothing."""
    spent = [s for s in spends if s.owner == team and s.left <= 0]
    frozen = sorted(s.slo for s in spent if not s.outside)
    if not frozen:
        spared = ", ".join(sorted(s.slo for s in spent))
        why = (
            f"{spared} spent by an outside cause; no freeze"
            if spared
            else "no budget exhausted"
        )
        return Verdict("budget", True, f"{team}: {why}")
    said = f"{team}: {', '.join(frozen)} exhausted"
    if labels & EXEMPT:
        allowed = ", ".join(sorted(labels & EXEMPT))
        return Verdict("budget", True, f"{said}; {allowed} ships")
    return Verdict("budget", False, f"{said}; release held")


PROMOTE, WAIT, ROLL_BACK = "PROMOTE", "WAIT", "ROLL BACK"


def _error(s: ReadableSpan) -> bool:
    return s.status.status_code is StatusCode.ERROR


def _mismatch(s: ReadableSpan) -> bool:
    return bool((s.attributes or {}).get(c.MODEL_MISMATCH))


Bad = Callable[[ReadableSpan], bool]
# Canary signals: when a chat span counts as bad, and the budget a
# regression must exceed. The pin lets no mismatch through.
SIGNALS: Mapping[str, tuple[Bad, float]] = {
    "errors": (_error, budget("availability")),
    "model_mismatch": (_mismatch, 0.0),
}


def populations(
    spans: Iterable[ReadableSpan], name: str
) -> dict[str, list[ReadableSpan]]:
    """Spans called `name`, split by the service.version of the
    release that emitted them."""
    split: dict[str, list[ReadableSpan]] = {}
    for s in spans:
        if s.name == name:
            v = str(s.resource.attributes.get(c.SERVICE_VERSION, ""))
            split.setdefault(v, []).append(s)
    return split


def decide(base: Rate, now: Rate, allowed: float) -> str:
    """Chapter 13's test, one-sided: roll back when the canary is
    worse than the control at z >= 3 and worse than the budget;
    wait while either side holds fewer than 30 events."""
    shift = rate_shift(base, now)
    if shift is None:
        return WAIT
    worse = shift.flagged and shift.statistic > 0
    return ROLL_BACK if worse and now.share > allowed else PROMOTE


@dataclass(frozen=True)
class Call:
    signal: str
    control: Rate
    canary: Rate
    decision: str


def canary(
    control: Sequence[ReadableSpan],
    new: Sequence[ReadableSpan],
    signals: Sequence[str] = tuple(SIGNALS),
) -> list[Call]:
    calls = []
    for name in signals:
        bad, allowed = SIGNALS[name]
        base = Rate(sum(map(bad, control)), len(control), name)
        now = Rate(sum(map(bad, new)), len(new), name)
        decision = decide(base, now, allowed)
        calls.append(Call(name, base, now, decision))
    return calls


def verdict(calls: Iterable[Call]) -> str:
    """One ROLL BACK decides; then one WAIT; else PROMOTE."""
    decisions = {call.decision for call in calls}
    for d in (ROLL_BACK, WAIT):
        if d in decisions:
            return d
    return PROMOTE


def changed(base: str) -> list[str]:
    """Paths changed since the branch left `base`."""
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.split()


def ci(base: str) -> int:
    """Run the gates the change needs; non-zero if any fails."""
    paths = changed(base)
    found = ", ".join(sorted(kinds(paths))) or "none"
    print(f"change types: {found}")
    failed = 0
    for gate in gates(paths):
        code = subprocess.run(COMMANDS[gate], check=False).returncode
        print(f"{gate}: {'passed' if code == 0 else 'FAILED'}")
        failed += code != 0
    return 1 if failed else 0
