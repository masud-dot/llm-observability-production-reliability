"""Snapshot the pinned GenAI conventions for the drift tests.

Clone open-telemetry/semantic-conventions-genai, check out the
commit in conventions.GENAI_COMMIT, then run:

    uv run python scripts/semconv_snapshot.py <checkout>

Writes src/wrenholt/telemetry/genai_snapshot.json: every attribute
and metric with its stability, plus span and event types.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "wrenholt" / "telemetry" / "genai_snapshot.json"


def snapshot(repo: Path) -> dict[str, Any]:
    commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    manifest_path = repo / "model" / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    attrs: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    spans: dict[str, str] = {}
    events: dict[str, str] = {}
    for path in sorted((repo / "model").rglob("*.yaml")):
        doc = yaml.safe_load(path.read_text()) or {}
        for a in doc.get("attributes") or []:
            if "key" in a:
                kind = a.get("type")
                kind = "enum" if isinstance(kind, dict) else str(kind)
                attrs[a["key"]] = {
                    "stability": a["stability"],
                    "type": kind,
                }
        for m in doc.get("metrics") or []:
            metrics[m["name"]] = {
                "stability": m["stability"],
                "instrument": m["instrument"],
                "unit": m["unit"],
            }
        for g in doc.get("spans") or []:
            spans[g["type"]] = g["stability"]
        for g in doc.get("events") or []:
            events[g["name"]] = g["stability"]
    return {
        "repository": "open-telemetry/semantic-conventions-genai",
        "commit": commit,
        "schema_url": manifest["schema_url"],
        "attributes": dict(sorted(attrs.items())),
        "metrics": dict(sorted(metrics.items())),
        "spans": dict(sorted(spans.items())),
        "events": dict(sorted(events.items())),
    }


if __name__ == "__main__":
    data = snapshot(Path(sys.argv[1]))
    OUT.write_text(json.dumps(data, indent=1) + "\n")
    counts = f"{len(data['attributes'])} attributes"
    counts += f", {len(data['metrics'])} metrics"
    print(f"{OUT.name}: {counts} @ {data['commit'][:7]}")
