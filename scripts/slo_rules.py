"""Write Prometheus's SLO recording rules from the SLO file
(Chapter 12), from the repository root.

uv run python scripts/slo_rules.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.slo.rules import RULES_PATH, render  # noqa: E402

if __name__ == "__main__":
    RULES_PATH.write_text(render(), encoding="utf-8")
    print(f"wrote {RULES_PATH.relative_to(ROOT)}")
