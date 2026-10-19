"""Run Chapter 19's game day from the repository root.

uv run python scripts/game_day.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.labs.game_day import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
