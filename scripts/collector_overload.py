"""Collector overload: accepted, then dropped (Chapter 10).

    uv run python scripts/collector_overload.py

Needs the pinned Collector: scripts/fetch_collector.sh, or set
OTELCOL_BIN. About 20 seconds; the workload is SIMULATED.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.labs.overload_lab import main  # noqa: E402

if __name__ == "__main__":
    main()
