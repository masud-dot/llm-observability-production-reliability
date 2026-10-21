"""Lab: the Collector is unreachable. Does Linnet keep serving?

    uv run python scripts/collector_outage.py

Mock provider A and a stand-in OTLP receiver run in this process;
Linnet runs as a child process with telemetry on. About two minutes.
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from services.mock_llm.server import running_provider  # noqa: E402
from services.otlp_standin import StandIn  # noqa: E402
from services.outage_lab import (  # noqa: E402
    REQUEST_SPAN,
    Linnet,
    free_port,
    run_phase,
    summarise,
)

PHASES: tuple[tuple[str, str, int], ...] = (
    ("healthy", "up", 3),
    ("refusing", "down", 20),
    ("hung", "hang", 25),
    ("healthy again", "up", 6),
)
STOPS: tuple[tuple[str, str, str | None, str], ...] = (
    (
        "healthy, no lifespan flush",
        "up",
        None,
        "services.noflush_app:app",
    ),
    ("healthy", "up", None, "wrenholt.api.main:app"),
    ("hung", "hang", None, "wrenholt.api.main:app"),
    ("hung, timeout 2 s", "hang", "2", "wrenholt.api.main:app"),
)


def stop_now(
    provider: str, mode: str, timeout: str | None, target: str
) -> tuple[float, int]:
    """SIGTERM straight after 10 requests: (seconds, spans kept)."""
    standin = StandIn(free_port())
    getattr(standin, mode)()
    api = Linnet(provider, standin.port, timeout, target)
    for _ in range(10):
        api.chat()
    seconds = api.stop()
    time.sleep(0.5)
    standin.down()
    kept = [n for _, _, n in standin.spans() if n == REQUEST_SPAN]
    return seconds, len(kept)


def main() -> None:
    standin = StandIn(free_port())
    with running_provider() as provider:
        standin.up()
        api = Linnet(provider.base_url, standin.port, None)
        for _ in range(5):  # warm-up, not measured
            api.chat()
        time.sleep(2)
        runs = []
        for name, mode, settle in PHASES:
            getattr(standin, mode)()
            runs.append(run_phase(name, api, standin, 30, settle))
        phases = summarise(runs, standin)
        warned = api.warnings()
        api.stop()
        standin.down()
        stops = [
            (label, *stop_now(provider.base_url, mode, t, target))
            for label, mode, t, target in STOPS
        ]
    print("Collector outage lab (mock provider: SIMULATED)")
    print(f"{'phase':<15}{'requests':>9}{'ok':>5}{'p95 ms':>8}"
          f"{'spans arrived':>15}")  # fmt: skip
    for p in phases:
        print(f"{p.name:<15}{p.requests:>9}{p.ok:>5}{p.p95_ms:>8.1f}"
              f"{p.arrived:>8} of {p.requests}")  # fmt: skip
    print(
        "SDK warnings: "
        + ", ".join(f"{v} {k}" for k, v in warned.items())
    )
    print("SIGTERM straight after 10 requests, receiver:")
    for label, seconds, kept in stops:
        timing = f"  {label:<28}{seconds:>5.1f} s"
        print(f"{timing}, spans kept {kept:>2} of 10")


if __name__ == "__main__":
    main()
