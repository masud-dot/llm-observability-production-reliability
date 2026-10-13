"""FS-05 lab (Chapter 12): malformed refund decisions (SIMULATED).

    uv run python scripts/fs05_malformed_refund.py

After a model update every refund decision carries the amount as
the customer wrote it, which the refund tool's schema refuses before
it runs. Linnet tells the customer that a person will check the
refund. Every answer arrives, on time and within its cost; only the
validity SLI, and the resolution SLI without an objective, see it.
"""

from decimal import Decimal

from wrenholt.labs.slo_lab import Hour, report, run
from wrenholt.slo import errorbudget


def main() -> None:
    before, after = run(), run(malformed=True)
    report(
        "FS-05: malformed refund decisions", "FS-05", before, after
    )
    burn = after.burn("decision_validity") or Decimal(1)
    minutes = errorbudget.lasts_hours(burn) * 60
    print(f"  at a burn rate of {burn:.0f}, the 28-day validity "
          f"budget lasts {minutes:.0f} minutes")  # fmt: skip


__all__ = ["Hour", "main", "run"]
