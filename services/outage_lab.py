"""Collector outage experiment: does Linnet keep serving? (Chapter 3)

Mock provider A and the stand-in OTLP receiver run in this
process; the Linnet API runs as a child process with telemetry on,
exactly as it would beside a real Collector. Each phase sends the
same requests and records what customers saw and which of that
phase's spans reached the receiver, however late.
"""

import json
import os
import signal
import socket
import statistics
import subprocess
import sys
import time
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from services.otlp_standin import StandIn

ROOT = Path(__file__).resolve().parents[1]
QUESTION = json.dumps({"message": "How long does a refund take?"})


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


# One server span per request. Since Chapter 4 a request also
# yields gateway, attempt and HTTP spans; the lab counts requests.
REQUEST_SPAN = "POST /chat"


@dataclass(frozen=True)
class Phase:
    name: str
    requests: int
    ok: int
    p95_ms: float
    arrived: int


class Linnet:
    """The Linnet API in a child process, telemetry on."""

    def __init__(
        self,
        provider: str,
        otlp_port: int,
        timeout_s: str | None,
        target: str = "wrenholt.api.main:app",
        *,
        name: str = "linnet-api",
        extra_env: Mapping[str, str] | None = None,
    ) -> None:
        self.port = free_port()
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(ROOT / "src"), str(ROOT)]
        )
        endpoint = f"http://127.0.0.1:{otlp_port}"
        env.update(
            WRENHOLT_PROVIDER_URL=provider,
            OTEL_SERVICE_NAME=name,
            OTEL_EXPORTER_OTLP_ENDPOINT=endpoint,
            OTEL_BSP_SCHEDULE_DELAY="1000",
            OTEL_METRIC_EXPORT_INTERVAL="1000",
        )
        env.pop("OTEL_EXPORTER_OTLP_TIMEOUT", None)
        if timeout_s is not None:
            env["OTEL_EXPORTER_OTLP_TIMEOUT"] = timeout_s
        env.update(extra_env or {})
        self.log = Path(os.environ.get("TMPDIR", "/tmp")) / (
            f"linnet-{self.port}.log"
        )
        command = [
            sys.executable, "-m", "uvicorn", target,
            "--app-dir", str(ROOT / "src"), "--port", str(self.port),
            "--log-level", "warning",
        ]  # fmt: skip
        with self.log.open("w") as sink:
            self.proc = subprocess.Popen(
                command, env=env, stdout=sink, stderr=sink
            )
        self._wait_ready()

    def _wait_ready(self) -> None:
        url = f"http://127.0.0.1:{self.port}/healthz"
        for _ in range(200):
            try:
                with urllib.request.urlopen(url, timeout=1):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("Linnet did not start")

    def chat(self) -> tuple[int, float]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/chat",
            data=QUESTION.encode(),
            headers={"Content-Type": "application/json"},
        )
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=10) as resp:
                status = int(resp.status)
        except OSError:
            status = 0
        return status, time.perf_counter() - start

    def ask(
        self, message: str, headers: Mapping[str, str] | None = None
    ) -> tuple[int, str]:
        """One chat with a chosen message and extra headers."""
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/chat",
            data=json.dumps({"message": message}).encode(),
            headers={
                "Content-Type": "application/json",
                **(headers or {}),
            },
        )
        with urllib.request.urlopen(request, timeout=10) as resp:
            return int(resp.status), resp.read().decode()

    def stop(self) -> float:
        """SIGTERM, then seconds until the process has exited."""
        start = time.perf_counter()
        self.proc.send_signal(signal.SIGTERM)
        self.proc.wait(timeout=120)
        return time.perf_counter() - start

    def warnings(self) -> dict[str, int]:
        text = self.log.read_text()
        return {
            "retries": text.count("Transient error"),
            "dropped batches": text.count("Failed to export"),
            "queue drops": text.count("Queue full"),
        }


def run_phase(
    name: str, api: Linnet, standin: StandIn, n: int, settle_s: float
) -> tuple[str, list[tuple[int, float]], int, int]:
    start_ns = time.time_ns()
    results = [api.chat() for _ in range(n)]
    end_ns = time.time_ns()
    time.sleep(settle_s)
    return name, results, start_ns, end_ns


def summarise(
    runs: list[tuple[str, list[tuple[int, float]], int, int]],
    standin: StandIn,
) -> list[Phase]:
    starts = [
        s for s, _, name in standin.spans() if name == REQUEST_SPAN
    ]
    phases = []
    for name, results, lo, hi in runs:
        times = sorted(seconds for _, seconds in results)
        p95 = statistics.quantiles(times, n=20)[-1] * 1000
        phases.append(
            Phase(
                name=name,
                requests=len(results),
                ok=sum(1 for status, _ in results if status == 200),
                p95_ms=p95,
                arrived=sum(1 for t in starts if lo <= t <= hi),
            )
        )
    return phases
