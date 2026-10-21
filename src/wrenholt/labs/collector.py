"""The real Collector, for the Chapter 10 labs.

The FS-15 and overload labs run the pinned otelcol-contrib 0.162.0:
its tail-sampling processor and export queues are what they study,
and nothing in Python stands in for them. The binary comes from
OTELCOL_BIN or .native/bin/otelcol-contrib, which
scripts/fetch_collector.sh downloads and checks.
"""

import os
import re
import subprocess
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any

import yaml

from services.outage_lab import free_port

ROOT = Path(__file__).resolve().parents[3]
OTELCOL = Path("deploy") / "compose" / "otelcol"
PRODUCTION = ROOT / OTELCOL / "config.production.yaml"
MISSING = (
    "This lab runs the pinned Collector, otelcol-contrib 0.162.0. "
    "Run scripts/fetch_collector.sh, or set OTELCOL_BIN."
)
_SAMPLE = re.compile(r"^([A-Za-z_:][\w:]*)(?:\{(.*)\})?\s+(\S+)$")
_LABEL = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')


def binary() -> Path | None:
    """The Collector binary, or None if it has not been fetched."""
    named = os.environ.get("OTELCOL_BIN")
    native = ROOT / ".native" / "bin" / "otelcol-contrib"
    path = Path(named) if named else native
    return path if path.is_file() else None


def production() -> dict[str, Any]:
    """deploy/compose/otelcol/config.production.yaml, parsed."""
    loaded: dict[str, Any] = yaml.safe_load(PRODUCTION.read_text())
    return loaded


@dataclass(frozen=True)
class Sample:
    """One line of the Collector's own Prometheus metrics."""

    name: str
    labels: dict[str, str]
    value: float


def parse(text: str) -> list[Sample]:
    samples = []
    for line in text.splitlines():
        found = _SAMPLE.match(line)
        if found is None or line.startswith("#"):
            continue
        name, labels, value = found.groups()
        samples.append(
            Sample(
                name, dict(_LABEL.findall(labels or "")), float(value)
            )
        )
    return samples


def total(samples: list[Sample], name: str, **labels: str) -> float:
    """The sum of every sample of one metric that has these labels."""
    return sum(
        s.value
        for s in samples
        if s.name == name
        and all(s.labels.get(k) == v for k, v in labels.items())
    )


class Collector:
    """One Collector process with a traces pipeline: an OTLP/HTTP
    receiver, the given processors, an OTLP/HTTP exporter."""

    def __init__(
        self,
        processors: dict[str, Any],
        backend: int,
        exporter: dict[str, Any] | None = None,
    ) -> None:
        self.receiver, self.health = free_port(), free_port()
        self.telemetry = free_port()
        here = "127.0.0.1"
        prometheus = {"host": here, "port": self.telemetry}
        reader = {"pull": {"exporter": {"prometheus": prometheus}}}
        config = {
            "extensions": {
                "health_check": {"endpoint": f"{here}:{self.health}"}
            },
            "receivers": {
                "otlp": {
                    "protocols": {
                        "http": {
                            "endpoint": f"{here}:{self.receiver}"
                        }
                    }
                }
            },
            "processors": processors,
            "exporters": {
                "otlp_http": {
                    "endpoint": f"http://{here}:{backend}",
                    **(exporter or {}),
                }
            },
            "service": {
                "extensions": ["health_check"],
                "telemetry": {"metrics": {"readers": [reader]}},
                "pipelines": {
                    "traces": {
                        "receivers": ["otlp"],
                        "processors": list(processors),
                        "exporters": ["otlp_http"],
                    }
                },
            },
        }
        self.folder = Path(tempfile.mkdtemp(prefix="otelcol-"))
        self.config = self.folder / "config.yaml"
        self.config.write_text(
            yaml.safe_dump(config, sort_keys=False)
        )
        self.log = self.folder / "collector.log"
        self._process: subprocess.Popen[bytes] | None = None

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.receiver}/v1/traces"

    def __enter__(self) -> "Collector":
        found = binary()
        if found is None:
            raise FileNotFoundError(MISSING)
        with self.log.open("wb") as out:
            self._process = subprocess.Popen(
                [str(found), f"--config={self.config}"],
                stdout=out,
                stderr=subprocess.STDOUT,
            )
        url = f"http://127.0.0.1:{self.health}/"
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=1):
                    return self
            except OSError:
                time.sleep(0.1)
        self.__exit__(None, None, None)
        raise RuntimeError(f"Collector not healthy; see {self.log}")

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        if self._process is not None:
            self._process.terminate()
            self._process.wait(timeout=60)
            self._process = None

    def metrics(self) -> list[Sample]:
        url = f"http://127.0.0.1:{self.telemetry}/metrics"
        with urllib.request.urlopen(url, timeout=5) as reply:
            return parse(reply.read().decode())
