# Phase 1.5 CI gate: local observability stack

**Status (1 October 2026): PASS.** GitHub Actions run #2 passed both
jobs, checks 1 to 9: https://github.com/masud-dot/llm-observability-production-reliability/actions/runs/36845252895
(commit 9b34e4a, triggered by push).

## Checks

| # | Check | How it is proved |
|---|---|---|
| 1 | Containers start | `docker compose up --wait`; Collector, Prometheus, Tempo and Loki readiness probes |
| 2 | Application healthy | Compose healthcheck, then `GET /healthz` |
| 3 | Telemetry reaches the Collector | Collector self-metrics: accepted spans, metric points and log records all above zero |
| 4 | Traces reach Tempo | `GET /api/v2/traces/<trace id>` returns the `smoke.request` span |
| 5 | Metrics reach Prometheus | PromQL `{__name__=~"smoke_requests.*"}` returns a series |
| 6 | Logs reach Loki | LogQL `{service_name="smoke-app"} \|= "<trace id>"` returns a stream |
| 7 | Grafana ready | `GET /api/health` reports the database ok; datasources `prometheus`, `tempo`, `loki` provisioned |
| 8 | Clean shutdown | `docker compose down --timeout 60`, then `docker compose ps --all` is empty |
| 9 | Provisioned alert delivered | alert-smoke job: rule `smoke_always_firing` provisioned from file; a notification reaches the webhook sink |

## GitHub Actions runs

| Run | Commit | Result | Notes |
|---|---|---|---|
| [#1](https://github.com/masud-dot/llm-observability-production-reliability/actions/runs/36844415794) | fd70bf9 | FAIL at check 1 | Docker Hub returned "manifest unknown" for `otel/opentelemetry-collector-contrib:0.162.0`: upstream published per-architecture tags only. The other images were interrupted, not rejected. |
| [#2](https://github.com/masud-dot/llm-observability-production-reliability/actions/runs/36845252895) | 9b34e4a | PASS, both jobs, about 4 minutes | Collector pulled from GHCR as `0.162.0-amd64`; version unchanged. Every check step succeeded; both log-dump steps were skipped. |

Step results for run #2 come from the public job pages; raw logs need
a GitHub sign-in.

## Repeating the gate

1. Push a change under `deploy/compose/`, `services/` or the smoke
   scripts, or run Actions, compose-smoke, Run workflow.
2. Record the run URL and both job results in Section 19 of the
   Phase 1 document.

Local equivalent with Docker Engine and Compose v5.5.1:

```bash
cd deploy/compose
docker compose config --quiet
docker compose up --detach --build --wait --wait-timeout 240
python3 ../../scripts/smoke_stack.py
docker compose down --volumes --remove-orphans --timeout 60
test -z "$(docker compose ps --all --quiet)"

export COMPOSE_FILE=docker-compose.yml:docker-compose.alerting.yml
docker compose up --detach --build --wait --wait-timeout 240
python3 ../../scripts/smoke_alert.py
docker compose down --volumes --remove-orphans --timeout 60
unset COMPOSE_FILE
```

## Sandbox evidence (supporting, not the gate)

Docker is not available in the Phase 1.5 sandbox. `scripts/native_smoke.sh`
ran the pinned Linux binaries (Collector 0.162.0, Prometheus 3.15.0,
Tempo 3.1.0, Loki 3.7.8) with the same configuration files, apart
from two host-local changes on temporary copies, and the smoke app on
the locked dependencies (CPython 3.14.4). Output, verbatim:

```text
PASS  1 collector health                HTTP 200 '{"status":"Server available","upSince":"2026-09-30'
PASS  1 prometheus ready                HTTP 200 'Prometheus Server is Ready.\n'
PASS  1 tempo ready                     HTTP 200 'ready\n'
PASS  1 loki ready                      HTTP 200 'ready\n'
PASS  2 app healthy                     HTTP 200 '{"status":"ok"}'
PASS  3 collector accepted all signals  accepted {'spans': 32.0, 'points': 11.0, 'records': 6.0}
PASS  4 trace reached tempo             /api/v2/traces/f31f85fa0b15... found
PASS  5 metric reached prometheus       1 series ['smoke_requests_total']
PASS  6 log reached loki                1 stream(s)
SKIP  7 grafana                         not part of this run
0 failed, 1 skipped, 10 total
      8 app exited within 1 s
      8 otelcol exited within 0 s
      8 prometheus exited within 0 s
      8 loki exited within 1 s
      8 tempo exited within 30 s
PASS  8 clean shutdown (native: every process exited on SIGTERM)
```

Static checks run in the sandbox on 30 September 2026:

- `otelcol-contrib validate` (0.162.0): configuration valid.
- `promtool check config` (3.15.0): configuration valid.
- Both Compose files validate against the Compose Specification JSON
  schema (main branch, fetched 30 September 2026).
- actionlint 1.7.12 with shellcheck 0.11.0 on the workflow: no problems found (exit 0).
- shellcheck 0.11.0 on `scripts/native_smoke.sh`: no findings.
- ruff 0.16.9 and mypy 2.3.1 `--strict`: no issues in four files.

Not covered by the sandbox, and since covered by GitHub Actions run
#2: image tags and pulls, the smoke-app image build, Compose
networking and service names, Grafana, and the alert job (check 9).

## Findings

- Collector 0.162.0 shipped without a multi-arch image tag (run #1).
  The stack pulls the GHCR `0.162.0-amd64` tag; ARM hosts need
  emulation or the `0.162.0-arm64` tag until a multi-arch tag is
  pinned in Phase 3.

- Tempo 3.1.0 in monolithic mode took about 30 s to exit after
  SIGTERM, because its backend worker waits out a job timeout; it then
  logged a clean stop. A 30 s stop timeout would have killed it, so
  the Compose file gives Tempo `stop_grace_period: 60s` and the
  workflow uses `down --timeout 60`.
- Idle monolithic Tempo logs `nil job received` errors from its
  backend worker. They did not affect ingestion or trace queries in
  this run.
