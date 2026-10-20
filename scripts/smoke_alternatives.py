"""Smoke checks for the Appendix H alternatives (mock provider:
SIMULATED). Stdlib only, like smoke_stack.py.

    python3 scripts/smoke_alternatives.py jaeger
        The stack with docker-compose.jaeger.yml: Linnet answers,
        and its traces reach Jaeger's query API.
    python3 scripts/smoke_alternatives.py lgtm
        Linnet run directly against grafana/otel-lgtm: its traces
        and its HTTP metric reach the bundled Tempo and Prometheus,
        queried through the bundled Grafana.
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


LINNET = env("SMOKE_LINNET", "http://localhost:8080")
JAEGER = env("SMOKE_JAEGER", "http://localhost:16686")
GRAFANA = env("SMOKE_GRAFANA", "http://localhost:3000")
TIMEOUT = float(env("SMOKE_TIMEOUT_S", "180"))
SERVICE = "linnet-api"
JOB = "wrenholt/linnet-api"  # <namespace>/<name> (Chapter 6)
QUESTION = {"message": "How long does a refund take?"}
RESULTS: list[tuple[str, str, str]] = []


def call(
    url: str,
    body: object | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    """Return (status, body). Status 0 means no connection."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data)
    request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            return int(resp.status), resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()
    except (urllib.error.URLError, OSError) as exc:
        return 0, str(exc)


def record(name: str, ok: bool, detail: str) -> bool:
    RESULTS.append((name, "PASS" if ok else "FAIL", detail[:110]))
    return ok


def poll(name: str, probe: Probe) -> bool:
    deadline = time.monotonic() + TIMEOUT
    ok, detail = False, "not attempted"
    while time.monotonic() < deadline:
        ok, detail = probe()
        if ok:
            break
        time.sleep(2.0)
    return record(name, ok, detail)


def linnet_answers() -> tuple[bool, str]:
    status, body = call(f"{LINNET}/chat", QUESTION)
    ok = status == 200 and "five working days" in body
    return ok, f"HTTP {status} {body[:60]!r}"


def jaeger_lists_linnet() -> tuple[bool, str]:
    status, body = call(f"{JAEGER}/api/services")
    names = (
        (json.loads(body).get("data") or []) if status == 200 else []
    )
    return SERVICE in names, f"HTTP {status}, services {names}"


def jaeger_has_traces() -> tuple[bool, str]:
    query = urllib.parse.urlencode(
        {"service": SERVICE, "limit": "20"}
    )
    status, body = call(f"{JAEGER}/api/traces?{query}")
    traces = (
        (json.loads(body).get("data") or []) if status == 200 else []
    )
    return bool(traces), f"HTTP {status}, {len(traces)} trace(s)"


def grafana(path: str) -> tuple[int, str]:
    """GET from Grafana: anonymously, then with the image's default
    admin login, which only a throwaway container may keep."""
    status, body = call(f"{GRAFANA}{path}")
    if status in (401, 403):
        token = base64.b64encode(b"admin:admin").decode()
        status, body = call(
            f"{GRAFANA}{path}",
            None,
            {"Authorization": f"Basic {token}"},
        )
    return status, body


def datasource(kind: str) -> str | None:
    status, body = grafana("/api/datasources")
    if status != 200:
        return None
    for d in json.loads(body):
        if d.get("type") == kind:
            return str(d.get("uid"))
    return None


def grafana_healthy() -> tuple[bool, str]:
    status, body = call(f"{GRAFANA}/api/health")
    return status == 200, f"HTTP {status} {body[:60]!r}"


def lgtm_has_traces() -> tuple[bool, str]:
    uid = datasource("tempo")
    if uid is None:
        return False, "no tempo data source"
    query = urllib.parse.urlencode(
        {"tags": f"service.name={SERVICE}", "limit": "20"}
    )
    status, body = grafana(
        f"/api/datasources/proxy/uid/{uid}/api/search?{query}"
    )
    traces = (
        json.loads(body).get("traces", []) if status == 200 else []
    )
    return bool(traces), f"HTTP {status}, {len(traces)} trace(s)"


def lgtm_has_metric() -> tuple[bool, str]:
    uid = datasource("prometheus")
    if uid is None:
        return False, "no prometheus data source"
    promql = (
        f'http_server_request_duration_seconds_count{{job="{JOB}"}}'
    )
    query = urllib.parse.urlencode({"query": promql})
    status, body = grafana(
        f"/api/datasources/proxy/uid/{uid}/api/v1/query?{query}"
    )
    series = (
        json.loads(body)["data"]["result"] if status == 200 else []
    )
    return bool(series), f"HTTP {status}, {len(series)} series"


def traffic() -> None:
    for _ in range(5):
        call(f"{LINNET}/chat", QUESTION)


def jaeger() -> None:
    poll("H.3 Linnet answers", linnet_answers)
    traffic()
    poll("H.3 Jaeger lists linnet-api", jaeger_lists_linnet)
    poll("H.3 Jaeger holds Linnet traces", jaeger_has_traces)


def lgtm() -> None:
    poll("H.4 Grafana healthy", grafana_healthy)
    poll("H.4 Linnet answers", linnet_answers)
    traffic()
    poll("H.4 Linnet traces in the bundled Tempo", lgtm_has_traces)
    poll("H.4 HTTP metric in the bundled Prometheus", lgtm_has_metric)


def main(argv: list[str]) -> int:
    modes = {"jaeger": jaeger, "lgtm": lgtm}
    if len(argv) != 1 or argv[0] not in modes:
        print("usage: smoke_alternatives.py jaeger|lgtm")
        return 2
    modes[argv[0]]()
    width = max(len(name) for name, _, _ in RESULTS)
    for name, status, detail in RESULTS:
        print(f"{status}  {name.ljust(width)}  {detail}")
    failed = sum(1 for _, status, _ in RESULTS if status == "FAIL")
    print(f"{failed} failed, {len(RESULTS)} total")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
