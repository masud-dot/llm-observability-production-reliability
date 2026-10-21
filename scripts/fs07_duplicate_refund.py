"""Run the Chapter 9 FS-07 lab from the repository root.

uv run python scripts/fs07_duplicate_refund.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.labs.fs07_lab import main  # noqa: E402

if __name__ == "__main__":
    main()
