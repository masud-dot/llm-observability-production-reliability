"""Smoke test for the local observability stack (checks 1-8).

Stdlib only, so it runs on a bare CI runner. Exit status 0 means
every required check passed. Endpoints default to the Compose
port mappings; override them with SMOKE_* environment variables.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

Probe = Callable[[], tuple[bool, str]]


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


APP = env("SMOKE_APP", "http://localhost:8000")
HEALTH = env("SMOKE_COLLECTOR_HEALTH", "http://localhost:13133/")
SELF = env("SMOKE_COLLECTOR_METRICS", "http://localhost:8888/metrics")
TEMPO = env("SMOKE_TEMPO", "http://localhost:3200")
PROM = env("SMOKE_PROMETHEUS", "http://localhost:9090")
LOKI = env("SMOKE_LOKI", "http://localhost:3100")
GRAFANA = env("SMOKE_GRAFANA", "http://localhost:3000")
AUTH = env("SMOKE_GRAFANA_AUTH", "admin:smoke-only-password")
SKIP_GRAFANA = env("SMOKE_SKIP_GRAFANA", "0") == "1"
TIMEOUT = float(env("SMOKE_TIMEOUT_S", "180"))

RESULTS: list[tuple[str, str, str]] = []


def http_get(url: str, auth: str | None = None) -> tuple[int, str]:
    """Return (status, body). Status 0 means no connection."""
    request = urllib.request.Request(url)
    request.add_header("Accept", "application/json")
    if auth:
        token = base64.b64encode(auth.encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            status = int(resp.status)
            return status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as exc:
        return 0, str(exc)


def record(name: str, status: str, detail: str) -> None:
    RESULTS.append((name, status, detail[:110]))


def poll(name: str, probe: Probe) -> bool:
    """Retry a probe every 2 s until it passes or time runs out."""
    deadline = time.monotonic() + TIMEOUT
    ok, detail = False, "not attempted"
    while time.monotonic() < deadline:
        ok, detail = probe()
        if ok:
            break
        time.sleep(2.0)
    record(name, "PASS" if ok else "FAIL", detail)
    return ok


def ready(url: str) -> Probe:
    def probe() -> tuple[bool, str]:
        status, body = http_get(url)
        return status == 200, f"HTTP {status} {body[:50]!r}"

    return probe


ACCEPTED = (
    "otelcol_receiver_accepted_spans",
    "otelcol_receiver_accepted_metric_points",
    "otelcol_receiver_accepted_log_records",
)


def collector_accepted() -> tuple[bool, str]:
    status, body = http_get(SELF)
    if status != 200:
        return False, f"HTTP {status}"
    totals = dict.fromkeys(ACCEPTED, 0.0)
    for line in body.splitlines():
        for name in ACCEPTED:
            if line.startswith(name):
                totals[name] += float(line.rsplit(" ", 1)[-1])
    short = {k.rsplit("_", 1)[-1]: v for k, v in totals.items()}
    return all(v > 0 for v in totals.values()), f"accepted {short}"


def tempo_has(trace_id: str) -> Probe:
    def probe() -> tuple[bool, str]:
        status = 0
        for path in ("/api/v2/traces/", "/api/traces/"):
            status, body = http_get(TEMPO + path + trace_id)
            if status == 200 and "smoke.request" in body:
                return True, f"{path}{trace_id[:12]}... found"
        return False, f"HTTP {status}"

    return probe


def prometheus_has_metric() -> tuple[bool, str]:
    query = '{__name__=~"smoke_requests.*"}'
    url = f"{PROM}/api/v1/query?" + urllib.parse.urlencode(
        {"query": query}
    )
    status, body = http_get(url)
    if status != 200:
        return False, f"HTTP {status}"
    series = json.loads(body)["data"]["result"]
    names = sorted({s["metric"]["__name__"] for s in series})
    return bool(series), f"{len(series)} series {names}"


def loki_has(trace_id: str) -> Probe:
    def probe() -> tuple[bool, str]:
        now = time.time_ns()
        selector = '{service_name="smoke-app"}'
        params = {
            "query": f'{selector} |= "{trace_id}"',
            "start": str(now - 15 * 60 * 10**9),
            "end": str(now),
            "limit": "5",
        }
        query = urllib.parse.urlencode(params)
        url = f"{LOKI}/loki/api/v1/query_range?{query}"
        status, body = http_get(url)
        if status != 200:
            return False, f"HTTP {status} {body[:60]!r}"
        streams = json.loads(body)["data"]["result"]
        return bool(streams), f"{len(streams)} stream(s)"

    return probe


def grafana_ready() -> tuple[bool, str]:
    status, body = http_get(f"{GRAFANA}/api/health")
    if status != 200:
        return False, f"HTTP {status}"
    health = json.loads(body)
    return health.get("database") == "ok", body[:80]


def grafana_datasources() -> tuple[bool, str]:
    status, body = http_get(f"{GRAFANA}/api/datasources", AUTH)
    if status != 200:
        return False, f"HTTP {status}"
    uids = {d["uid"] for d in json.loads(body)}
    wanted = {"prometheus", "tempo", "loki"}
    return wanted <= uids, f"uids {sorted(uids)}"


def smoke_request() -> str:
    status, body = http_get(f"{APP}/smoke")
    if status != 200:
        raise RuntimeError(f"/smoke returned HTTP {status}")
    return str(json.loads(body)["trace_id"])


def main() -> int:
    poll("1 collector health", ready(HEALTH))
    poll("1 prometheus ready", ready(f"{PROM}/-/ready"))
    poll("1 tempo ready", ready(f"{TEMPO}/ready"))
    poll("1 loki ready", ready(f"{LOKI}/ready"))
    if poll("2 app healthy", ready(f"{APP}/healthz")):
        trace_id = [smoke_request() for _ in range(3)][-1]
        poll("3 collector accepted all signals", collector_accepted)
        poll("4 trace reached tempo", tempo_has(trace_id))
        poll("5 metric reached prometheus", prometheus_has_metric)
        poll("6 log reached loki", loki_has(trace_id))
    else:
        for step in ("3", "4", "5", "6"):
            record(f"{step} blocked", "FAIL", "app not healthy")
    if SKIP_GRAFANA:
        record("7 grafana", "SKIP", "not part of this run")
    else:
        poll("7 grafana ready", grafana_ready)
        poll("7 grafana datasources", grafana_datasources)
    width = max(len(name) for name, _, _ in RESULTS)
    for name, status, detail in RESULTS:
        print(f"{status}  {name.ljust(width)}  {detail}")
    failed = sum(1 for _, status, _ in RESULTS if status == "FAIL")
    skipped = sum(1 for _, status, _ in RESULTS if status == "SKIP")
    print(f"{failed} failed, {skipped} skipped, {len(RESULTS)} total")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
