"""Run the Chapter 5 rename drill from the repository root.

uv run python scripts/rename_drill.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.labs.rename_drill import main  # noqa: E402

if __name__ == "__main__":
    main()
