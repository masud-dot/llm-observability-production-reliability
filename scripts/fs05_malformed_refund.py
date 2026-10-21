"""Run the Chapter 12 FS-05 lab from the repository root.

uv run python scripts/fs05_malformed_refund.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.labs.fs05_lab import main  # noqa: E402

if __name__ == "__main__":
    main()
