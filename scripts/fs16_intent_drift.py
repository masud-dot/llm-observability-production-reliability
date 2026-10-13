"""Run the Chapter 13 FS-16 lab from the repository root.

uv run python scripts/fs16_intent_drift.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.labs.fs16_lab import main  # noqa: E402

if __name__ == "__main__":
    main()
