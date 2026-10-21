"""Run the Chapter 11 FS-12 lab from the repository root.

uv run python scripts/fs12_token_explosion.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.labs.fs12_lab import main  # noqa: E402

if __name__ == "__main__":
    main()
