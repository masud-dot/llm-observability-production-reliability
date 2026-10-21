"""The request map: steps, budgets and dependencies of a journey."""

from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from wrenholt.slo.events import Journey, RequestClass

LayerTag = Literal["L1", "L2", "L3", "L4"]
REQUEST_MAP_PATH = Path(__file__).with_name("request_map.yaml")


class Step(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    component: str
    layers: tuple[LayerTag, ...]
    budget_s: float = Field(ge=0)
    depends_on: tuple[str, ...] = ()


class Dependency(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    component: str
    critical: bool


class RequestMap(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    journey: Journey
    request_class: RequestClass
    deadline_s: float = Field(gt=0)
    first_chunk_after: str
    steps: tuple[Step, ...]
    dependencies: tuple[Dependency, ...]

    @model_validator(mode="after")
    def check_rules(self) -> Self:
        step_ids = [s.id for s in self.steps]
        dep_ids = {d.id for d in self.dependencies}
        if self.first_chunk_after not in step_ids:
            raise ValueError("first_chunk_after must name a step")
        for step in self.steps:
            if unknown := set(step.depends_on) - dep_ids:
                raise ValueError(f"{step.id}: unknown {unknown}")
        if self.budget_through(step_ids[-1]) > self.deadline_s:
            raise ValueError("step budgets exceed the deadline")
        return self

    def budget_through(self, step_id: str) -> float:
        """Cumulative budget up to and including one step."""
        total = 0.0
        for step in self.steps:
            total += step.budget_s
            if step.id == step_id:
                return round(total, 3)
        raise KeyError(step_id)

    def ids(self) -> set[str]:
        """Every step and dependency where an SLI can be measured."""
        steps = {s.id for s in self.steps}
        return steps | {d.id for d in self.dependencies}


def load_request_map(path: Path = REQUEST_MAP_PATH) -> RequestMap:
    with path.open(encoding="utf-8") as handle:
        return RequestMap.model_validate(yaml.safe_load(handle))
