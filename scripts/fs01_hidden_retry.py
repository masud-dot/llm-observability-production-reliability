"""Run the FS-01 lab from the repository root.

uv sync --group lab
uv run python scripts/fs01_hidden_retry.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.labs.fs01 import main  # noqa: E402

if __name__ == "__main__":
    main()
