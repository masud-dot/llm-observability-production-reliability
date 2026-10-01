# llm-observability-production-reliability

Companion repository for *LLM Observability & Production AI
Reliability*. This is the Phase 1.5 skeleton: the frozen technical
baseline and the CI gate for the local stack. Chapter code arrives
from Phase 2 onwards.

- `versions.toml`: frozen versions with release and verification
  dates, stability and Phase 3 recheck flags.
- `uv.lock`: produced by uv 0.11.7 from the exact pins in
  `pyproject.toml`.
- `deploy/compose/`: the locked local stack (OpenTelemetry
  Collector, Prometheus, Tempo, Loki, Grafana). Jaeger is a
  documented alternative only.
- `.github/workflows/compose-smoke.yml`: the Phase 1.5 gate.
- `docs/PHASE-1.5-CI.md`: exact run sequence and current status.
