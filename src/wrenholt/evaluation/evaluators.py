"""Evaluators and the adapter for outside ones (Chapter 13).

SIMULATED: these evaluators are rules, not judges. They exist so
that results flow through Wrenholt's telemetry. Wrenholt needs only
this from an evaluator: a name, a version, and a label from a small
closed set for each result. An LLM judge plugs in behind the same
protocol, through `External`.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from wrenholt.rag.corpus import TODAY, snapshot

WINDOW = re.compile(r"returned within (\d+) days")
NUMBER = re.compile(r"\d+(?:\.\d+)?")
DECLINED = re.compile(
    r"\bcan(?:not|'t) (?:help|confirm|answer)\b", re.IGNORECASE
)
ORDER = re.compile(r"\bWG-\d{6}\b")
POLICY_WORDS = ("return", "policy", "warranty", "delivery")


@dataclass(frozen=True)
class Sample:
    """One answer and what it stood on. In process only."""

    question: str
    answer: str
    passages: tuple[str, ...]
    prompt_version: str
    index_version: str


@dataclass(frozen=True)
class Verdict:
    name: str
    label: str
    score: float | None = None


class Evaluator(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def version(self) -> str: ...
    @property
    def labels(self) -> tuple[str, ...]: ...

    def evaluate(self, sample: Sample) -> Verdict | None:
        """A verdict, or None when the evaluator does not apply."""
        ...


class Intent:
    name, version = "intent", "1"
    labels: tuple[str, ...] = ("policy", "order", "refund", "other")

    def evaluate(self, sample: Sample) -> Verdict:
        asked = sample.question.lower()
        if "refund" in asked:
            label = "refund"
        elif ORDER.search(sample.question) or "order" in asked:
            label = "order"
        elif any(word in asked for word in POLICY_WORDS):
            label = "policy"
        else:
            label = "other"
        return Verdict(self.name, label)


class Refusal:
    name, version = "refusal", "1"
    labels: tuple[str, ...] = ("answer", "refusal")

    def evaluate(self, sample: Sample) -> Verdict:
        refused = DECLINED.search(sample.answer) is not None
        label = "refusal" if refused else "answer"
        return Verdict(self.name, label, 0.0 if refused else 1.0)


class Groundedness:
    """Policy answers only: every number the answer states appears
    in the passages it was written from."""

    name, version = "groundedness", "1"
    labels: tuple[str, ...] = ("grounded", "ungrounded")

    def evaluate(self, sample: Sample) -> Verdict | None:
        if Intent().evaluate(sample).label != "policy":
            return None
        found = set(NUMBER.findall(" ".join(sample.passages)))
        grounded = set(NUMBER.findall(sample.answer)) <= found
        label = "grounded" if grounded else "ungrounded"
        return Verdict(self.name, label, 1.0 if grounded else 0.0)


def window_in_force(as_of: str = TODAY) -> int:
    """The returns window the help centre has in force."""
    for article in snapshot(as_of):
        stated = WINDOW.search(article.text)
        if article.version.startswith("returns-") and stated:
            return int(stated.group(1))
    raise LookupError("no returns policy in force")


class PolicyAccuracy:
    """Answers that state a returns window: is it the one in force?"""

    name, version = "policy_accuracy", "1"
    labels: tuple[str, ...] = ("correct", "incorrect")

    def __init__(self, days: int) -> None:
        self.days = days

    def evaluate(self, sample: Sample) -> Verdict | None:
        stated = WINDOW.search(sample.answer)
        if stated is None:
            return None
        correct = int(stated.group(1)) == self.days
        label = "correct" if correct else "incorrect"
        return Verdict(self.name, label, 1.0 if correct else 0.0)


@dataclass(frozen=True)
class External:
    """An evaluator outside Wrenholt: its labels mapped onto a closed
    set of Wrenholt's, its score kept, its version recorded."""

    name: str
    version: str
    labels: tuple[str, ...]
    judge: Callable[[Sample], Mapping[str, object]]
    label_map: Mapping[str, str]

    def evaluate(self, sample: Sample) -> Verdict:
        raw = self.judge(sample)
        label = self.label_map.get(str(raw.get("label")))
        if label is None or label not in self.labels:
            raise ValueError(f"{self.name}: unmapped label {raw!r}")
        score = raw.get("score")
        value = (
            float(score) if isinstance(score, int | float) else None
        )
        return Verdict(self.name, label, value)


def standard() -> list[Evaluator]:
    """Wrenholt's evaluators, in the order they run."""
    return [
        Intent(),
        Refusal(),
        Groundedness(),
        PolicyAccuracy(window_in_force()),
    ]
