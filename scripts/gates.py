"""Release gates and the self-assessment (Chapter 20).

uv run --group lab python scripts/gates.py ci --base origin/main
uv run --group lab python scripts/gates.py evaluate
uv run --group lab python scripts/gates.py lab      # SIMULATED
uv run --group lab python scripts/gates.py assess
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt import gates, maturity  # noqa: E402
from wrenholt.labs import gate_lab  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gates")
    parser.add_argument(
        "command", choices=("ci", "evaluate", "lab", "assess")
    )
    parser.add_argument("--base", default="origin/main")
    args = parser.parse_args(argv)
    if args.command == "ci":
        return gates.ci(args.base)
    if args.command == "evaluate":
        return gate_lab.evaluate()
    if args.command == "lab":
        gate_lab.main()
        return 0
    return maturity.main()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
