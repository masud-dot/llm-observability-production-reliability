"""Wrenholt's command line (Chapter 15): diagnose an incident from
recorded telemetry, then reproduce one request from its bundle.

uv run python scripts/wrenholt_cli.py diagnose [FIXTURE]
uv run python scripts/wrenholt_cli.py replay TRACE --reader NAME
    --role investigator --reason TEXT
uv run python scripts/wrenholt_cli.py record
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt import diagnosis  # noqa: E402
from wrenholt.labs import diagnosis_lab as lab  # noqa: E402
from wrenholt.privacy.vault import Reader  # noqa: E402

CURRENT = "45e99498.wrenholt-embed-1"  # the build that should serve


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(prog="wrenholt")
    sub = cli.add_subparsers(dest="command", required=True)
    d = sub.add_parser("diagnose", help="attribute the layer")
    d.add_argument("fixture", nargs="?", default=str(lab.FIXTURE))
    r = sub.add_parser("replay", help="reproduce one request")
    r.add_argument("trace")
    r.add_argument("--reader", required=True)
    r.add_argument("--role", default="investigator")
    r.add_argument("--reason", default="")
    sub.add_parser("record", help="record the fixture again")
    args = cli.parse_args(argv)
    if args.command == "record":
        lab.record()
        print(f"wrote {lab.FIXTURE.relative_to(ROOT)}")
        return 0
    if args.command == "diagnose":
        traces = diagnosis.load(Path(args.fixture))
        print("\n".join(diagnosis.report(traces)))
        return 0
    by_id = {t["trace"]: t for t in diagnosis.load(lab.FIXTURE)}
    bundle = by_id[args.trace]["bundle"]
    who = Reader(args.reader, args.role, "wrenholt")
    v = lab.vault()
    try:
        asked = lab.question(v, args.trace, who, args.reason)
    except PermissionError as denied:
        print(f"vault: {denied}")
        return 1
    print(f"vault: granted to {who.name}; logged with the reason")
    for index in ("", CURRENT):
        got = lab.replay(bundle, asked, index)
        print(
            f"replay on {got.index_version}: {got.documents}"
            f" passages, grounded {str(got.grounded).lower()}"
        )
    print(
        f"bundle: prompt {bundle['prompt_version']},"
        f" index {bundle['index_version']},"
        f" model {bundle['requested_model']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
