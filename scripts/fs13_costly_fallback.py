"""Run the Chapter 11 FS-13 lab from the repository root.

uv run python scripts/fs13_costly_fallback.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.labs.fs13_lab import main  # noqa: E402

if __name__ == "__main__":
    main()
