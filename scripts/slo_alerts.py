"""Write the SLO burn-rate alerts from the SLO file (Chapter 14),
from the repository root: Grafana's provisioning file, and the same
alerts as Prometheus rules for promtool's tests.

uv run python scripts/slo_alerts.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from wrenholt.slo import alerts  # noqa: E402

if __name__ == "__main__":
    for path, document in (
        (alerts.GRAFANA_PATH, alerts.grafana()),
        (alerts.PROMETHEUS_PATH, alerts.prometheus()),
    ):
        path.write_text(alerts.render(document), encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
