"""The SLI catalog: what Linnet counts, layer by layer.

The catalog is YAML so that product owners can review it
without reading Python. This module loads it and rejects a
catalog that breaks the rules below.
"""

from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from wrenholt.slo.events import Journey, RequestClass

Layer = Literal["L1", "L2", "L3", "L4"]
Kind = Literal[
    "availability",
    "latency",
    "validity",
    "groundedness",
    "freshness",
    "resolution",
]
CATALOG_PATH = Path(__file__).with_name("sli_catalog.yaml")


class SliSpec(BaseModel):
    """One candidate SLI: good events over valid events."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    layer: Layer
    kind: Kind
    good: str
    valid: str
    journeys: tuple[Journey, ...]
    measured_at: str
    source: str
    thresholds_s: dict[RequestClass, float] = Field(
        default_factory=dict
    )


class Catalog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int
    min_events: int = Field(gt=0)
    slis: tuple[SliSpec, ...]

    @model_validator(mode="after")
    def check_rules(self) -> Self:
        ids = [s.id for s in self.slis]
        if len(ids) != len(set(ids)):
            raise ValueError("SLI ids must be unique")
        if {s.layer for s in self.slis} != {"L1", "L2", "L3", "L4"}:
            raise ValueError("every layer needs at least one SLI")
        for s in self.slis:
            if (s.kind == "latency") != bool(s.thresholds_s):
                raise ValueError(
                    f"{s.id}: thresholds belong on latency SLIs only"
                )
        return self

    def get(self, sli_id: str) -> SliSpec:
        return next(s for s in self.slis if s.id == sli_id)


def load_catalog(path: Path = CATALOG_PATH) -> Catalog:
    with path.open(encoding="utf-8") as handle:
        return Catalog.model_validate(yaml.safe_load(handle))
