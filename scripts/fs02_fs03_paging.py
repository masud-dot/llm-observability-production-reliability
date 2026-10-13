"""FS-02 and FS-03 against the burn-rate alerts (Chapter 14): which
alerts fire, how soon, and how much budget is gone by then.

uv run python scripts/fs02_fs03_paging.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.labs.paging_lab import main  # noqa: E402

if __name__ == "__main__":
    main()
