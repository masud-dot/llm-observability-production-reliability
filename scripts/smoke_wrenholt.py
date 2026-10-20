"""Smoke checks for the application plane (Chapters 3 and 5).

Stdlib only, like smoke_stack.py. The default run makes checks
10-15 and 18 against a running stack. --collector-down (check 16)
expects the Collector to be stopped and Linnet still answering;
--collector-recovered (check 17) expects telemetry to flow again.
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
PROVIDER_A = env("SMOKE_PROVIDER_A", "http://localhost:8101")
PROVIDER_B = env("SMOKE_PROVIDER_B", "http://localhost:8102")
ORDERS = env("SMOKE_ORDERS", "http://localhost:8200")
HEALTH = env("SMOKE_COLLECTOR_HEALTH", "http://localhost:13133/")
SELF = env("SMOKE_COLLECTOR_METRICS", "http://localhost:8888/metrics")
TEMPO = env("SMOKE_TEMPO", "http://localhost:3200")
PROM = env("SMOKE_PROMETHEUS", "http://localhost:9090")
GRAFANA = env("SMOKE_GRAFANA", "http://localhost:3000")
AUTH = env("SMOKE_GRAFANA_AUTH", "admin:smoke-only-password")
DASHBOARD = "wrenholt-llm-gateway"
TIMEOUT = float(env("SMOKE_TIMEOUT_S", "180"))
DELIVERED = "WG-100006"  # first delivered order in the dataset
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


def healthy(base: str) -> Probe:
    def probe() -> tuple[bool, str]:
        status, _ = call(f"{base}/healthz")
        return status == 200, f"{base} HTTP {status}"

    return probe


def ask() -> tuple[int, str, float]:
    start = time.perf_counter()
    status, body = call(f"{LINNET}/chat", QUESTION)
    return status, body, time.perf_counter() - start


def linnet_answers() -> tuple[bool, str]:
    status, body, _ = ask()
    ok = status == 200 and "five working days" in body
    return ok, f"HTTP {status} {body[:60]!r}"


def provider_b_serves_its_model() -> tuple[bool, str]:
    req = {
        "model": "mock-b-standard",
        "messages": [{"role": "user", "content": "refund?"}],
    }
    b_status, b_body = call(f"{PROVIDER_B}/v1/chat/completions", req)
    a_status, _ = call(f"{PROVIDER_A}/v1/chat/completions", req)
    model = (
        json.loads(b_body).get("model") if b_status == 200 else None
    )
    ok = model == "mock-b-standard-2026-09" and a_status == 404
    return ok, f"B {b_status} {model}; A {a_status}"


def orders_refund_is_idempotent() -> tuple[bool, str]:
    status, body = call(f"{ORDERS}/orders/{DELIVERED}")
    if status != 200:
        return False, f"lookup HTTP {status}"
    refund = {"order_id": DELIVERED, "amount_minor": 500}
    key = {"Idempotency-Key": "smoke-refund-1"}
    first = call(f"{ORDERS}/refunds", refund, key)
    again = call(f"{ORDERS}/refunds", refund, key)
    ids = {json.loads(b).get("refund_id") for _, b in (first, again)}
    ok = first[0] in (200, 201) and again[0] == 200 and len(ids) == 1
    return ok, f"HTTP {first[0]} then {again[0]}, refund {ids}"


def tempo_has_linnet_spans() -> tuple[bool, str]:
    query = urllib.parse.urlencode(
        {"tags": "service.name=linnet-api", "limit": "20"}
    )
    status, body = call(f"{TEMPO}/api/search?{query}")
    traces = (
        json.loads(body).get("traces", []) if status == 200 else []
    )
    return bool(traces), f"HTTP {status}, {len(traces)} trace(s)"


def prometheus_has_linnet_metric() -> tuple[bool, str]:
    # Chapter 6 added service.namespace, and Prometheus names an
    # OTLP job "<namespace>/<name>": the series must exist under it.
    promql = (
        "http_server_request_duration_seconds_count"
        '{job="wrenholt/linnet-api"}'
    )
    query = urllib.parse.urlencode({"query": promql})
    status, body = call(f"{PROM}/api/v1/query?{query}")
    series = (
        json.loads(body)["data"]["result"] if status == 200 else []
    )
    return bool(series), f"HTTP {status}, {len(series)} series"


def dashboard_provisioned() -> tuple[bool, str]:
    token = base64.b64encode(AUTH.encode()).decode()
    headers = {"Authorization": f"Basic {token}"}
    status, body = call(
        f"{GRAFANA}/api/search?tag=wrenholt", None, headers
    )
    uids = (
        [d.get("uid") for d in json.loads(body)]
        if status == 200
        else []
    )
    return DASHBOARD in uids, f"HTTP {status}, dashboards {uids}"


def accepted_spans() -> float:
    status, body = call(SELF)
    if status != 200:
        return -1.0
    name = "otelcol_receiver_accepted_spans"
    lines = [x for x in body.splitlines() if x.startswith(name)]
    return sum(float(x.rsplit(" ", 1)[-1]) for x in lines)


def default_checks() -> None:
    for base in (LINNET, PROVIDER_A, PROVIDER_B, ORDERS):
        poll(f"10 healthy {base}", healthy(base))
    poll("11 Linnet answers via provider A", linnet_answers)
    poll(
        "12 provider B serves only its model",
        provider_b_serves_its_model,
    )
    poll(
        "13 orders lookup and idempotent refund",
        orders_refund_is_idempotent,
    )
    poll("14 Linnet spans reached Tempo", tempo_has_linnet_spans)
    poll(
        "15 Linnet HTTP metric reached Prometheus",
        prometheus_has_linnet_metric,
    )
    poll("18 gateway dashboard provisioned", dashboard_provisioned)


def collector_down() -> None:
    status, _ = call(HEALTH)
    if not record(
        "16 Collector is down", status == 0, f"HTTP {status}"
    ):
        return
    results = [ask() for _ in range(20)]
    ok = sum(1 for status, _, _ in results if status == 200)
    worst = max(seconds for _, _, seconds in results)
    detail = f"{ok}/20 answered, slowest {worst * 1000:.0f} ms"
    record(
        "16 Linnet keeps serving", ok == 20 and worst < 1.0, detail
    )


def collector_recovered() -> None:
    poll("17 Collector healthy again", healthy(HEALTH.rstrip("/")))
    before = accepted_spans()
    for _ in range(5):
        ask()

    def resumed() -> tuple[bool, str]:
        now = accepted_spans()
        return (
            now >= before + 5,
            f"accepted spans {before:.0f} -> {now:.0f}",
        )

    poll("17 telemetry resumes", resumed)


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "--collector-down":
        collector_down()
    elif mode == "--collector-recovered":
        collector_recovered()
    else:
        default_checks()
    width = max(len(name) for name, _, _ in RESULTS)
    for name, status, detail in RESULTS:
        print(f"{status}  {name.ljust(width)}  {detail}")
    failed = sum(1 for _, status, _ in RESULTS if status == "FAIL")
    print(f"{failed} failed, {len(RESULTS)} total")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
