"""Run the Chapter 4 gateway comparison lab from the repo root.

uv sync --group lab
uv run python scripts/gateway_lab.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.labs.gateway_lab import main  # noqa: E402

if __name__ == "__main__":
    main()
