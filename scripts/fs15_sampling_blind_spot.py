"""FS-15: quiet failures under tail sampling (Chapter 10).

    uv run python scripts/fs15_sampling_blind_spot.py

Needs the pinned Collector: scripts/fetch_collector.sh, or set
OTELCOL_BIN. About a minute; mock provider output is SIMULATED.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.labs.fs15_lab import main  # noqa: E402

if __name__ == "__main__":
    main()
