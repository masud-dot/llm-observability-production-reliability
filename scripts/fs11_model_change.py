"""Run the Chapter 6 FS-11 lab from the repository root.

uv run python scripts/fs11_model_change.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.labs.fs11_lab import main  # noqa: E402

if __name__ == "__main__":
    main()
