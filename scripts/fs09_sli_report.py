"""Print the FS-09 SLI evidence from the repository root.

uv run python scripts/fs09_sli_report.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.slo.catalog import load_catalog  # noqa: E402
from wrenholt.slo.fs09 import report  # noqa: E402

if __name__ == "__main__":
    print(report(load_catalog()))
