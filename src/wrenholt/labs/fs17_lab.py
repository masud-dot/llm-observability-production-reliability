"""FS-17 lab (Chapter 12): guardrail over-blocking (SIMULATED).

    uv run python scripts/fs17_over_blocking.py

Guardrail version 2 adds a rule meant for scripted refund fraud. It
refuses every customer who says how much they want back. Refusals
are fast, available and free, so the latency, availability and
cost SLIs improve; the refusal budget burns, and the validity SLI
loses its events.
"""

from decimal import Decimal

from wrenholt.labs.slo_lab import Hour, report, run
from wrenholt.slo import errorbudget


def main() -> None:
    before, after = run(), run(guardrail="2")
    report("FS-17: guardrail over-blocking", "FS-17", before, after)
    burn = after.burn("not_refused") or Decimal(1)
    hours = errorbudget.lasts_hours(burn)
    print(f"  at a burn rate of {burn:.0f}, the 28-day refusal "
          f"budget lasts {hours:.1f} hours")  # fmt: skip
    was, now = before.per_resolved, after.per_resolved
    print(f"  cost per resolved ticket (USD): {was:.7f} -> {now:.7f}")


__all__ = ["Hour", "main", "run"]
