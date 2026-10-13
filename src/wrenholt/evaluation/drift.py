"""Version-sliced drift checks (Chapter 13).

Each check compares a slice, such as a prompt or index version, with
a baseline, and says nothing until both have enough results. Results
from different evaluator versions are never compared: a new
evaluator is a new sensor, and its scores start a new baseline.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass

MIN_RESULTS = 30  # the SLI catalogue's minimum


@dataclass(frozen=True)
class Rate:
    hits: int  # results with the label watched, such as refusal
    n: int  # all results
    evaluator: str

    @property
    def share(self) -> float:
        return self.hits / self.n


@dataclass(frozen=True)
class Mix:
    counts: Mapping[str, int]  # results by label, such as intent
    evaluator: str

    @property
    def n(self) -> int:
        return sum(self.counts.values())

    def share(self, label: str) -> float:
        return self.counts.get(label, 0) / self.n


@dataclass(frozen=True)
class Shift:
    statistic: float
    flagged: bool


def same_sensor(base: str, current: str) -> None:
    if base != current:
        raise ValueError(
            f"{base}, {current}: a new evaluator needs a new baseline"
        )


def rate_shift(
    base: Rate,
    current: Rate,
    z: float = 3.0,
    min_n: int = MIN_RESULTS,
) -> Shift | None:
    """A two-proportion z-test of current against base."""
    same_sensor(base.evaluator, current.evaluator)
    if base.n < min_n or current.n < min_n:
        return None
    pooled = (base.hits + current.hits) / (base.n + current.n)
    spread = pooled * (1 - pooled) * (1 / base.n + 1 / current.n)
    diff = current.share - base.share
    if spread == 0:
        return Shift(0.0 if diff == 0 else math.inf, diff != 0)
    score = diff / math.sqrt(spread)
    return Shift(score, abs(score) >= z)


def mix_shift(
    base: Mix,
    current: Mix,
    threshold: float = 0.1,
    min_n: int = MIN_RESULTS,
) -> Shift | None:
    """Total variation distance: the share of results whose label
    would have to change for the mixes to match."""
    same_sensor(base.evaluator, current.evaluator)
    if base.n < min_n or current.n < min_n:
        return None
    labels = set(base.counts) | set(current.counts)
    distance = (
        sum(abs(current.share(x) - base.share(x)) for x in labels) / 2
    )
    return Shift(distance, distance >= threshold)
