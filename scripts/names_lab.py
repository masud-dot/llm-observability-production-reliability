"""Run the Chapter 5 names lab from the repository root.

uv sync --group lab
uv run python scripts/names_lab.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.labs.names_lab import main  # noqa: E402

if __name__ == "__main__":
    main()
