"""Phase 1.5 alert smoke: a file-provisioned Grafana alert rule
must reach the webhook sink. Stdlib only."""

from __future__ import annotations

import json
import os
import sys

from smoke_stack import (
    AUTH,
    GRAFANA,
    RESULTS,
    http_get,
    poll,
    ready,
)

SINK = os.environ.get("SMOKE_SINK", "http://localhost:8099")
RULE = "smoke_always_firing"


def rule_provisioned() -> tuple[bool, str]:
    url = f"{GRAFANA}/api/v1/provisioning/alert-rules/{RULE}"
    status, body = http_get(url, AUTH)
    return status == 200, f"HTTP {status} {body[:60]!r}"


def notification_received() -> tuple[bool, str]:
    status, body = http_get(f"{SINK}/received")
    if status != 200:
        return False, f"HTTP {status}"
    count = int(json.loads(body)["count"])
    return count >= 1, f"{count} notification(s)"


def main() -> int:
    poll("9 grafana ready", ready(f"{GRAFANA}/api/health"))
    poll("9 alert rule provisioned", rule_provisioned)
    poll("9 notification reached webhook", notification_received)
    failed = 0
    for name, status, detail in RESULTS:
        print(f"{status}  {name}  {detail}")
        failed += status == "FAIL"
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
