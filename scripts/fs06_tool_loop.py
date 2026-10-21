"""Run the Chapter 9 FS-06 lab from the repository root.

uv run python scripts/fs06_tool_loop.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.labs.fs06_lab import main  # noqa: E402

if __name__ == "__main__":
    main()
