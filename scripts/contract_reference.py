"""Write, or check, the telemetry contract reference (Appendix A).

uv run python scripts/contract_reference.py [--check]
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.telemetry.reference import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
