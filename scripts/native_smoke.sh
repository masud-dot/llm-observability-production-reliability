#!/usr/bin/env bash
# Native-binary smoke run without Docker (Phase 1.5 sandbox only).
#
# Uses the same Collector, Prometheus, Tempo and Loki files as the
# Compose stack, with two host-local changes on temporary copies:
# Tempo's OTLP port becomes 4418 (the Collector owns 4318 on one
# host) and the Prometheus scrape target becomes localhost:8888.
# Grafana publishes no Linux binary on GitHub releases, so check 7
# is skipped. This is evidence for the configurations only; it is
# NOT the GitHub Actions gate.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="${BIN:-$ROOT/.native/bin}"
CFG="$ROOT/deploy/compose"
WORK="$(mktemp -d)"
declare -A PIDS=()

start() {
  local name="$1"; shift
  "$@" >"$WORK/$name.log" 2>&1 &
  PIDS[$name]=$!
}

alive() {
  local state
  state="$(ps -o stat= -p "$1" 2>/dev/null)"
  [[ -n "$state" && "$state" != Z* ]]
}

sed 's/0.0.0.0:4318/0.0.0.0:4418/' "$CFG/tempo/tempo.yaml" \
  >"$WORK/tempo.yaml"
sed 's/otel-collector:8888/localhost:8888/' \
  "$CFG/prometheus/prometheus.yml" >"$WORK/prometheus.yml"
rm -rf /tmp/tempo /tmp/loki

start tempo "$BIN/tempo" -config.file="$WORK/tempo.yaml"
start loki "$BIN/loki" -config.file="$CFG/loki/loki.yaml"
start prometheus "$BIN/prometheus" \
  --config.file="$WORK/prometheus.yml" \
  --storage.tsdb.path="$WORK/prom" --web.enable-otlp-receiver
start otelcol env TEMPO_OTLP_HTTP=http://localhost:4418 \
  PROM_OTLP_HTTP=http://localhost:9090/api/v1/otlp \
  LOKI_OTLP_HTTP=http://localhost:3100/otlp \
  "$BIN/otelcol-contrib" --config="$CFG/otelcol/config.yaml"
start app env OTEL_SERVICE_NAME=smoke-app \
  OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
  OTEL_METRIC_EXPORT_INTERVAL=2000 \
  "$ROOT/.venv/bin/uvicorn" app:app \
  --app-dir "$ROOT/services/smoke_app" --port 8000

SMOKE_SKIP_GRAFANA=1 SMOKE_TIMEOUT_S="${SMOKE_TIMEOUT_S:-120}" \
  python3 "$ROOT/scripts/smoke_stack.py"
rc=$?

# Check 8 (native form): stop in dependency order, as Compose does:
# app, then Collector, then backends; each gets 60 s after SIGTERM.
clean=0
stop() {
  local name t0
  for name in "$@"; do kill -TERM "${PIDS[$name]}" 2>/dev/null || true; done
  t0=$SECONDS
  for name in "$@"; do
    while alive "${PIDS[$name]}" && (( SECONDS - t0 < 60 )); do
      sleep 1
    done
    if alive "${PIDS[$name]}"; then
      echo "FAIL  8 $name still running 60 s after SIGTERM"
      kill -KILL "${PIDS[$name]}" 2>/dev/null || true
      clean=1
    else
      echo "      8 $name exited within $(( SECONDS - t0 )) s"
    fi
  done
}
stop app
stop otelcol
stop prometheus loki tempo
if (( clean == 0 )); then
  echo "PASS  8 clean shutdown (native: every process exited on SIGTERM)"
else
  rc=1
fi
if (( rc != 0 )); then
  for f in "$WORK"/*.log; do echo "== $f"; tail -n 15 "$f"; done
fi
echo "logs kept in $WORK"
exit "$rc"
