"""The SLO file: Wrenholt's objectives (Chapter 12).

Like the SLI catalogue, the file is YAML that product owners can
review, loaded by pydantic models that reject unknown fields. The
rules below are the ones a reviewer would otherwise have to check
by eye.
"""

from decimal import Decimal
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from wrenholt.slo.catalog import Layer
from wrenholt.slo.events import RequestClass
from wrenholt.telemetry import conventions as c

OBJECTIVES_PATH = Path(__file__).with_name("objectives.yaml")
# Where the good and valid events are counted: the API's SLI events,
# its first-chunk histogram, the tool histogram's refund calls, the
# gateway's attempts, or evaluation results (Chapter 13).
Counted = Literal[
    "events", "first_chunk", "refund_calls", "attempts", "evaluation"
]


class Slo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    slo: str
    sli: str = ""  # the SLI it counts, when not the same id
    layer: Layer
    counted_by: Counted
    objective: Decimal | None = Field(default=None, gt=0, lt=1)
    owner: str | None = None
    reason: str | None = None  # why there is no objective
    request_class: RequestClass | None = None
    threshold_s: float | None = None
    max_cost_usd: Decimal | None = None
    bad_label: str | None = None  # Chapter 13: an evaluation's

    @property
    def sli_id(self) -> str:
        return self.sli or self.slo

    @property
    def budget(self) -> Decimal:
        if self.objective is None:
            raise ValueError(f"{self.slo} has no objective")
        return 1 - self.objective

    @model_validator(mode="after")
    def check_rules(self) -> Self:
        if (self.objective is None) == (self.reason is None):
            raise ValueError(f"{self.slo}: an objective or a reason")
        if (self.objective is None) != (self.owner is None):
            raise ValueError(
                f"{self.slo}: an objective needs an owner"
            )
        timed = self.counted_by == "first_chunk"
        if timed != (self.threshold_s is not None):
            raise ValueError(
                f"{self.slo}: thresholds are for latency"
            )
        if timed and self.request_class is None:
            raise ValueError(f"{self.slo}: which request class?")
        if timed and self.threshold_s not in c.ANSWER_BUCKETS:
            # PromQL can only count at a bucket boundary.
            raise ValueError(f"{self.slo}: not a bucket boundary")
        if self.counted_by == "events" and (
            self.sli_id not in c.EVENT_SLIS
        ):
            raise ValueError(
                f"{self.slo}: the API judges no such SLI"
            )
        if (self.sli_id == "answer_cost") != bool(self.max_cost_usd):
            raise ValueError(f"{self.slo}: a cost threshold, once")
        return self

    @model_validator(mode="after")
    def check_evaluation(self) -> Self:
        """Chapter 13: an SLI counted from evaluation results names
        the label that makes a result bad."""
        judged = self.counted_by == "evaluation"
        if judged != (self.bad_label is not None):
            raise ValueError(
                f"{self.slo}: a bad label, for evaluations"
            )
        return self


class Objectives(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int
    window: Literal["28d"]
    objectives: tuple[Slo, ...]

    @model_validator(mode="after")
    def check_ids(self) -> Self:
        ids = [s.slo for s in self.objectives]
        if len(ids) != len(set(ids)):
            raise ValueError("SLO ids must be unique")
        return self

    def get(self, slo: str) -> Slo:
        return next(s for s in self.objectives if s.slo == slo)


def load_objectives(path: Path = OBJECTIVES_PATH) -> Objectives:
    with path.open(encoding="utf-8") as handle:
        return Objectives.model_validate(yaml.safe_load(handle))
