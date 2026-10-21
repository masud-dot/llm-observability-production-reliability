"""Past the breaking point (Chapter 18, SIMULATED).

    uv run python scripts/breaking_lab.py

Chapter 17's surge model, driven by the load generator's patterns:
answers take 2 s, a process has room for 90 at once (45 a second),
and one question in four is a refund. A gradual ramp finds the
breaking point; an impulse shows how each design recovers after it.
"""

import heapq
from collections.abc import Sequence
from dataclasses import dataclass

from wrenholt.api.admission import Admission
from wrenholt.diagnosis import quantile
from wrenholt.labs.protect_lab import DEADLINE_S
from wrenholt.load import gradual, impulse

SERVICE, SLOTS, RESERVED, SLO_S = 2.0, 90, 18, 2.5


@dataclass(frozen=True)
class Served:
    arrival: float
    outcome: str  # full, degraded or failed
    latency: float  # arrival to answer, for full answers


def serve(times: Sequence[float], admit: bool) -> list[Served]:
    free = [0.0] * SLOTS  # when each place is next free (queue)
    admission, ends = Admission(SLOTS, RESERVED), list[float]()
    out = []
    for i, now in enumerate(times):
        critical = i % 4 == 3
        if admit:
            while ends and ends[0] <= now:
                heapq.heappop(ends)
                admission.release()
            cls = "critical_action" if critical else "interactive"
            if admission.admit(cls):
                heapq.heappush(ends, now + SERVICE)
                out.append(Served(now, "full", SERVICE))
            else:
                missed = "failed" if critical else "degraded"
                out.append(Served(now, missed, 0.0))
            continue
        start = max(now, free[0])
        if start + SERVICE > now + DEADLINE_S:
            out.append(Served(now, "failed", 0.0))
            continue
        heapq.heapreplace(free, start + SERVICE)
        out.append(Served(now, "full", start + SERVICE - now))
    return out


@dataclass(frozen=True)
class Window:
    start: int
    rate: float  # arrivals a second
    full: int
    degraded: int
    failed: int
    p95_s: float  # full answers; 0 when there are none


def windows(
    served: Sequence[Served], width: int, seconds: int
) -> list[Window]:
    out = []
    for start in range(0, seconds, width):
        w = [s for s in served if start <= s.arrival < start + width]
        full = sorted(s.latency for s in w if s.outcome == "full")
        out.append(
            Window(
                start,
                len(w) / width,
                len(full),
                sum(s.outcome == "degraded" for s in w),
                sum(s.outcome == "failed" for s in w),
                round(quantile(full, 0.95), 2) if full else 0.0,
            )
        )
    return out


def healthy(w: Window) -> bool:
    return w.failed == 0 and w.p95_s <= SLO_S


def ramp(admit: bool) -> list[Window]:
    """0 to 120 a second over two minutes, in 20 s windows."""
    return windows(serve(gradual(0, 120, 120), admit), 20, 120)


def spike(admit: bool) -> list[Window]:
    """30 a second, and 120 for 10 s from 40 s, in 5 s windows."""
    times = impulse(30, 120, at=40, width=10, seconds=120)
    return windows(serve(times, admit), 5, 120)


def recovered(ws: list[Window], after: int = 50) -> int | None:
    """The start of the first healthy window after the impulse,
    with every window after it healthy too."""
    tail = [w for w in ws if w.start >= after]
    for i, w in enumerate(tail):
        if all(healthy(x) for x in tail[i:]):
            return w.start
    return None


def report() -> list[str]:
    lines = [
        "gradual, 0 to 120 a second over 120 s; room for 45 a second",
        f"{'':12}{'queue':^19}{'admission':^26}",
        f"{'from':<5}{'rate':>7}{'full':>6}{'fail':>6}{'p95 s':>7}"
        f"{'full':>7}{'degr':>6}{'fail':>6}{'p95 s':>7}",
    ]
    for q, a in zip(ramp(False), ramp(True), strict=True):
        lines.append(
            f"{q.start:>3} s{q.rate:>7.1f}{q.full:>6,}{q.failed:>6,}"
            f"{q.p95_s:>7.2f}{a.full:>7,}{a.degraded:>6,}{a.failed:>6,}"
            f"{a.p95_s:>7.2f}"
        )
    lines.append("impulse, 30 a second, 120 from 40 s to 50 s:")
    for name, admit in (("queue", False), ("admission", True)):
        ws = spike(admit)
        failed = sum(w.failed for w in ws)
        degraded = sum(w.degraded for w in ws)
        back = recovered(ws)
        lost = f"{failed:>4,} failed, {degraded:>4,} degraded"
        lines.append(f"  {name:<10}{lost}, healthy from {back} s")
    return lines


def main() -> int:
    print("\n".join(report()))
    return 0
