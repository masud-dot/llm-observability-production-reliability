"""Run Chapter 16's protective-controls lab from the repository root.

uv run python scripts/protect_lab.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.labs.protect_lab import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
