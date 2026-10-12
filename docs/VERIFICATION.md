# Verification log

Every listing in the book maps to a file, the test or command that
checks it, an interpreter, a date and a result. Phase 2 rows were
executed in the authoring sandbox. Phase 3 repeats every row before
publication, and the book uses the words "tested" and "verified"
only for rows recorded here. Results from the mock provider are
SIMULATED.

## Chapter 1: Why LLM Systems Fail Differently

- Command: `make verify-ch01` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` as frozen in Phase 1.5, then amended by
  decision 17 (see below); groups dev + lab
- Date: 2026-10-01

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L01-01 | FS-01 fault plan | `services/mock_llm/faults.py` | `tests/unit/test_mock_provider.py` | pass | pending |
| L01-02 | Mock provider fault injection and request log | `services/mock_llm/app.py` | `tests/unit/test_mock_provider.py`, `tests/unit/test_baseline_smoke.py` | pass | pending |
| L01-03 | Linnet baseline answer path (SDK defaults) | `src/wrenholt/orchestrator/baseline.py` | `tests/unit/test_baseline_smoke.py`, `tests/unit/test_retry_layers_multiply.py` | pass | pending |
| L01-04 | Layered default instrumentation | `src/wrenholt/labs/layered.py` | `tests/lab/test_fs01_hidden_retry.py` | pass | pending |
| L01-05 | FS-01 lab output | `scripts/fs01_hidden_retry.py` | run command; output matches the listing except millisecond timings | pass (SIMULATED) | pending |
| L01-06 | Manual three-terminal run | `services/mock_llm/main.py`, `src/wrenholt/api/main.py` | executed as printed; reply in about 2 s; mock log 429, 429, 200 with retry counts 0, 1, 2 | pass (SIMULATED) | pending |
| L01-07 | Blind-spot test | `tests/lab/test_fs01_hidden_retry.py` | itself (2 tests) | pass | pending |

Same run, other checks:

- `pytest tests/unit tests/lab`: 8 passed. This includes
  `test_retry_layers_multiply.py`, which checks the worked number
  in Section 1.3: two application-level calls under persistent
  rate limiting reach the provider six times.
- Without the lab group, `tests/unit` passes (5 tests) and
  `tests/lab` stops with a usage error that names the missing
  group, so the blind-spot test cannot be skipped silently.
- `ruff check` and `ruff format --check`: clean on Chapter 1 files.
  `mypy --strict`: clean on 25 source files across `src`,
  `services`, `scripts` and `tests`.
- Timing variance: three runs of the FS-01 lab gave GenAI span
  durations of 2,020.0, 2,022.5 and 2,019.3 ms. The two 1 s
  retry-after waits dominate. Listing L01-05 and Figure 1.2 use
  the 2,019.3 ms run.

## Baseline amendment: decision 17 (2026-10-01)

`pyyaml==6.0.3` (runtime) and `types-pyyaml==6.0.12.20260906` (dev)
were added. The blueprint keeps failure scenarios, the SLI catalogue
and SLO specifications in YAML, and the Phase 1.5 lock had no YAML
parser. PyYAML 6.0.3 (released 2025-09-25) is the latest release and
ships CPython 3.12 to 3.14 wheels for Linux, macOS and Windows.

- Lock diff: 94 to 96 packages; two added, none removed, no existing
  version changed. `uv lock --check` passes.
- Re-verification on the amended lock (2026-10-01 20:27 UTC, CPython
  3.14.4): `import yaml` reports 6.0.3 with the libyaml C extension;
  ruff, ruff format and `mypy --strict` (25 files) clean; 8 tests
  passed; the FS-01 lab reproduced (2,020.9 ms; 429, 429, 200).
- The Compose stack is unaffected: the smoke app pins its own
  requirements. The Compose smoke workflow re-runs on the next push.

## Chapter 2: A Four-Layer Reliability Model for LLM Applications

- Command: `make verify-ch02` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` with decision 17 (96 packages); the
  Chapter 2 code needs only the default dev group
- Date: 2026-10-02

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L02-01 | Request map: deadline, budgets, dependencies | `src/wrenholt/slo/request_map.yaml` | `tests/slo/test_catalog_and_map.py` | pass | pending |
| L02-02 | SLI catalog entries | `src/wrenholt/slo/sli_catalog.yaml` | `tests/slo/test_catalog_and_map.py`, `tests/slo/test_sli_calculators.py` | pass | pending |
| L02-03 | `SliResult` and the low-traffic guard | `src/wrenholt/slo/sli.py` | `tests/slo/test_sli_calculators.py` | pass | pending |
| L02-04 | Rules and counting | `src/wrenholt/slo/sli.py` | `tests/slo/test_sli_calculators.py`, `tests/slo/test_fs09_slis.py` | pass | pending |
| L02-05 | FS-09 SLI report | `scripts/fs09_sli_report.py` | run command; output identical to the listing | pass (SIMULATED) | pending |
| L02-06 | FS-09 worked numbers | `tests/slo/test_fs09_slis.py` | itself | pass | pending |

Same run, other checks:

- `pytest tests/unit tests/lab tests/slo`: 23 passed; `uv run pytest
  tests/slo` on its own: 15 passed.
- Worked numbers under test: availability 4 of 6 valid; a 3.0 s
  first chunk failing the 2.5 s interactive threshold and passing
  the 4.0 s critical-action one; freshness 2 of 3; the night hour's
  11 of 12 with no ratio below the 30-event minimum; FS-09 freshness
  54 of 90 (60 per cent) and resolution 96 of 120 (80 per cent)
  against 114 of 120 (95 per cent) in the normal hour; request-map
  budgets of 9.2 s within the 10.0 s deadline and a first chunk by
  4.0 s.
- `ruff check`, `ruff format --check` and `mypy --strict` (35 source
  files): clean. Code identifiers use American spelling (`catalog`).
- Figure 2.1 is drawn from `request_map.yaml` by the figure script,
  so its budgets are the tested ones.

## Chapter 3: The Reference Architecture and the Wrenholt Baseline

- Command: `make verify-ch03` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages); `tests/lab` needs
  the `lab` group
- Date: 2026-10-02

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L03-01 | `linnet-api` service | `deploy/compose/docker-compose.yml` | `tests/unit/test_config_lint.py`; `docker compose config` (v5.5.1); native run of checks 10-17 | pass; Compose run in CI pending the push | pending |
| L03-02 | `start_telemetry()` | `src/wrenholt/telemetry/setup.py` | `tests/unit/test_telemetry_setup.py`, `tests/resilience/test_collector_outage.py`; native run | pass | pending |
| L03-03 | Lifespan flush | `src/wrenholt/telemetry/setup.py` | `tests/resilience/test_collector_outage.py` | pass | pending |
| L03-04 | FastAPI's built-in telemetry off | `src/wrenholt/telemetry/framework.py` | `tests/unit/test_telemetry_setup.py`; single-request probe: 1 span per request (2 before) | pass | pending |
| L03-05 | Collector outage lab | `scripts/collector_outage.py` | run command; output identical to the listing | pass (workload SIMULATED; SDK behaviour measured) | pending |
| L03-06 | CI checks 16-17 | `.github/workflows/compose-smoke.yml` | workflow parses; same checks run natively against the real Collector | pass natively; CI run pending the push | pending |
| L03-07 | Uvicorn and the flush | `tests/resilience/test_collector_outage.py` | itself | pass | pending |
| L03-08 | Config lint rules | `tests/unit/test_config_lint.py` | itself | pass | pending |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience`: 43 passed, 1 skipped
  (`promtool` not on `PATH`; it passes when present, and CI runs it
  in the Prometheus image); `pytest tests/lab`: 2 passed. 46 tests.
- Config lint with the native binaries: 13 of 13 passed, including
  `otelcol-contrib validate` (0.162.0) and `promtool check config`
  (3.15.0).
- `docker compose config --quiet` with the pinned v5.5.1 binary:
  valid. Docker is not available in the sandbox, so the image build
  and the Compose run of checks 10-17 happen in CI after the push.
- Native run, 2026-10-02 11:40 UTC: Collector 0.162.0, Tempo 3.1.0,
  Prometheus 3.15.0 and Loki 3.7.8 binaries with the Compose
  configuration files, plus the four application services. Checks
  10-15 passed (Tempo search found a Linnet trace; Prometheus held
  `http_server_request_duration_seconds_count{job="linnet-api"}`).
  Check 16, Collector stopped: 20 of 20 answered, slowest 7 ms.
  Check 17, Collector restarted: accepted spans 20 -> 25. Linnet's
  exit with the lifespan flush: 0.21 s.
- Outage lab, 2026-10-02 11:33-11:35 UTC: the output in L03-05.
- Behaviours of pinned packages, read from source and confirmed by
  execution (`versions.toml`, `[behaviours]`; decisions 19-21):
  FastAPI 0.142.1 adds its own exporters to existing providers;
  uvicorn 0.54.0 re-raises SIGTERM (exit code -15, atexit skipped);
  the OTLP/HTTP exporter 1.45.0 reads `OTEL_EXPORTER_OTLP_TIMEOUT`
  in seconds, where the specification (configuration/common.md,
  read 2026-10-02) defines milliseconds; the FastAPI
  instrumentation 0.66b0 emits the old HTTP names unless opted in;
  SDK 1.45.0 does not use `OTEL_BSP_EXPORT_TIMEOUT`.
- Orders dataset: 5,000 orders, seed 20260930, hash
  `722ade62ca223c77` (`data/hashes.toml`), regenerated by
  `tests/unit/test_orders_service.py`.
- `ruff check`, `ruff format --check` and `mypy --strict` (55 source
  files): clean. `uv lock --check`: 96 packages, unchanged.
- Figure 3.2 and Table 3.1 are generated from the Compose,
  Collector, Prometheus and Grafana files and from `versions.toml`
  by the figure script, so their values are the ones under test.

## Chapter 4: Instrumenting the LLM Gateway with OpenTelemetry

- Command: `make verify-ch04` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages); the comparison
  lab and `tests/lab` need the `lab` group
- Date: 2026-10-06

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L04-01 | Closed `error.type` set and retry rules | `src/wrenholt/gateway/errors.py` | `tests/unit/test_error_map.py` | pass | pending |
| L04-02 | OpenAI-compatible classifier | `src/wrenholt/gateway/openai_compat.py` | `tests/unit/test_error_map.py` (19 cases) | pass | pending |
| L04-03 | Retry policy | `src/wrenholt/gateway/policy.py` | `tests/unit/test_error_map.py`, `tests/unit/test_gateway_contract.py` | pass | pending |
| L04-04 | Request span and retry loop | `src/wrenholt/gateway/client.py` | `tests/unit/test_gateway_contract.py` | pass | pending |
| L04-05 | Attempt span on failure and success | `src/wrenholt/gateway/client.py` | `tests/unit/test_gateway_contract.py` | pass | pending |
| L04-06 | Gateway comparison lab | `scripts/gateway_lab.py` | run command (2026-10-06 02:51 UTC); `tests/lab/test_gateway_comparison.py` | pass (SIMULATED); counts identical on re-run, timings vary by milliseconds | pending |
| L04-07 | FS-18 contract test | `tests/unit/test_gateway_contract.py` | itself | pass | pending |
| L04-08 | Prometheus and TraceQL queries | none (queries) | native run, 2026-10-06 02:56 UTC | pass natively; Compose run pending the push | pending |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience`: 72 passed, 1 skipped
  (`promtool` not on `PATH`); `pytest tests/lab`: 5 passed. 78 tests:
  unit 55, slo 15, resilience 3, lab 5.
- `ruff check`, `ruff format --check` and `mypy --strict` with the
  lab group (70 source files): clean. `uv lock --check`: 96 packages.
- Every source listing in Chapters 1 to 4 is still verbatim in the
  repository. Chapter 1's L01-06 commands re-run on the Chapter 4
  code: the same answer and the same 429, 429, 200 sequence, now with
  SDK retry counts 0, 0, 0, because the gateway owns the retries.
- Native run, 2026-10-06 02:56 UTC: Collector 0.162.0, Prometheus
  3.15.0, Tempo 3.1.0 and Loki 3.7.8 with the Compose configuration,
  Linnet through the gateway, provider A on FS-01. One FS-01 chat took
  2.10 s and answered. Prometheus held
  `wrenholt_gateway_attempts_total` (2 with `error_type="rate_limited"`,
  2 without) and `gen_ai_client_operation_duration_seconds_*`.
  TraceQL `{ span.wrenholt.gateway.attempt_count > 1 }` and
  `{ span.error.type = "rate_limited" }` each found the FS-01 trace
  (2,089 ms) about 14 s after the request. A `rate()` ratio over the
  same counter was undefined in this short run (no increase between
  exports) and is not used in the chapter.
- Chapter 3's outage lab re-run on the Chapter 4 code (2026-10-06
  01:41 UTC): the same pattern as L03-05 (30, 0, 0 and 30 request spans
  arrived; 0 of 10 kept without the flush and 10 of 10 with it; 20.6 s
  and 4.5 s exits against a hung receiver). The harness now counts one
  server span per request, because a request produces four spans.
- Specification text read at semantic-conventions-genai `bcc7f9c`
  (checked out 2026-10-06); OpenAI error codes and Claude API errors
  pages read 2026-10-06; openai 3.22.1 retry logic read from the
  installed source (`versions.toml`, `[behaviours]`).
- Figure 4.1 and Table 4.1 are drawn from one captured FS-01 run
  through the gateway (`capture_fs01.py`, `fs01_gateway_spans.json`).

## Chapter 5: GenAI Semantic Conventions and the Compatibility Module

- Command: `make verify-ch05` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages); the names lab and
  `tests/lab` need the `lab` group; three drift tests need `promtool`
  on `PATH` and `SEMCONV_GENAI_DIR` pointing at a pinned checkout
- Date: 2026-10-06

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L05-01 | The registry | `src/wrenholt/telemetry/conventions.py` | `tests/drift/test_conventions_drift.py` | pass | pending |
| L05-02 | Snapshot check | `src/wrenholt/telemetry/drift.py` | `tests/drift/test_conventions_drift.py`, `tests/drift/test_rename_drill.py` | pass | pending |
| L05-03 | Names lab | `scripts/names_lab.py` | run command (2026-10-06 08:17 UTC; identical at 08:55); `tests/lab/test_names_lab.py` | pass (SIMULATED workload) | pending |
| L05-04 | Rename drill | `scripts/rename_drill.py` | run command (08:17 UTC; identical at 08:55); `tests/drift/test_rename_drill.py` | pass (SIMULATED workload) | pending |
| L05-05 | Drift tests | `tests/drift/test_conventions_drift.py` | itself | pass | pending |
| L05-06 | CI drift step | `.github/workflows/compose-smoke.yml` | workflow parses; the same suite run locally with `promtool` and the checkout: 17 passed | pass locally; CI run pending the push | pending |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience tests/drift`: 86
  passed, 4 skipped (no `promtool` on `PATH`, `SEMCONV_GENAI_DIR`
  unset). With `promtool` 3.15.0 and the pinned checkout, the drift
  suite: 17 passed. `pytest tests/lab`: 8 passed. 98 tests: unit 55,
  slo 15, resilience 3, drift 17, lab 8.
- `ruff check`, `ruff format --check` and `mypy --strict` with the
  lab group (82 source files): clean. `uv lock --check`: 96 packages.
- Every source listing in Chapters 1 to 5 is still verbatim in the
  repository.
- `genai_snapshot.json` regenerated from a checkout of
  semantic-conventions-genai at `bcc7f9c` is identical to the
  committed file: 86 attributes, 22 metrics, 13 span types and 3
  events, schema `gen-ai-dev/1.42.0-dev`. The commit is the same in
  `conventions.py`, `versions.toml` and the workflow (tested).
- Core conventions changelog, v1.42.0, read 2026-10-06: the GenAI
  conventions moved to their own repository; the tag commit
  (`ae3a986`) is dated 2026-06-12.
- `promtool test rules`: grouping by a label no series carries
  returns one series with no labels, not an error; `promtool check
  rules` parses every dashboard expression.
- The LLM gateway dashboard lints clean against the registry and
  against a real gateway run. Grafana itself does not run in the
  sandbox: smoke check 18 confirms provisioning in CI after the push.
- Figure 5.1 and Tables 5.1 and 5.2 are generated by
  `figures_ch05.py` from the snapshot, the registry and a fresh
  capture of the official instrumentation's names
  (`official_names.json`).

## Chapter 6: Context Propagation, Correlation and Reproducibility

- Command: `make verify-ch06` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages); `tests/lab` needs
  the `lab` group
- Date: 2026-10-06

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L06-01 | Trace-context-only propagation | `src/wrenholt/telemetry/setup.py` | `tests/unit/test_correlation.py` | pass | pending |
| L06-02 | The model pin check | `src/wrenholt/gateway/client.py` | `tests/unit/test_fs11.py`; drift suite | pass | pending |
| L06-03 | Recording the bundle off the request path | `src/wrenholt/repro.py` | `tests/unit/test_correlation.py`, `tests/unit/test_repro.py` | pass | pending |
| L06-04 | Correlation lab | `scripts/correlation_lab.py` | run command (2026-10-06 09:10 UTC); `tests/unit/test_correlation.py` | pass (SIMULATED workload); IDs differ per run | pending |
| L06-05 | FS-11 lab | `scripts/fs11_model_change.py` | run command (14:58 UTC); `tests/unit/test_fs11.py` | pass (SIMULATED workload) | pending |
| L06-06 | Correlation test | `tests/unit/test_correlation.py` | itself | pass | pending |
| L06-07 | Exemplar, trace and log queries | none (queries) | native run, 2026-10-06 14:53 UTC | pass natively; Compose run pending the push | pending |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience tests/drift`: 97
  passed, 4 skipped (no `promtool` on `PATH`; `SEMCONV_GENAI_DIR`
  unset). With `promtool` and the pinned checkout the drift suite: 17
  passed. `pytest tests/lab`: 8 passed. 109 tests: unit 66, slo 15,
  resilience 3, drift 17, lab 8.
- `ruff check`, `ruff format --check` and `mypy --strict` with the
  lab group (97 source files): clean. `uv lock --check`: 96 packages.
  `docker compose config` (v5.5.1): valid.
- Every source listing in Chapters 1 to 6 is verbatim in the
  repository. L05-01 shows the registry as of Chapter 5; Chapter 6
  appends four entries, and the Chapter 5 entries remain a verbatim
  prefix (checked).
- Native run, 2026-10-06 14:53 UTC: Collector 0.162.0, Prometheus
  3.15.0 with `--enable-feature=exemplar-storage`, Tempo 3.1.0, Loki
  3.7.8, the orders service and Linnet. One order chat with upstream
  baggage. Prometheus returned one exemplar on
  `gen_ai_client_operation_duration_seconds_bucket` with `trace_id`
  and `span_id`; Tempo returned that trace (5 spans in `linnet-api`,
  1 in `orders`); Loki returned its line `chat answered`, and the
  bundle record with `trace_id` and `wrenholt_repro_bundle` as
  structured metadata.
- Read 2026-10-06: W3C Trace Context Recommendation; OpenTelemetry
  baggage documentation. Installed source: the API's default
  `OTEL_PROPAGATORS` (`tracecontext,baggage`) and the SDK's default
  exemplar filter (`trace_based`), recorded in `versions.toml`.
- A reproduction bundle is 527 bytes of JSON (FS-11 lab).
- Figures 6.1 and 6.2 and Table 6.1 are drawn by `figures_ch06.py`
  from the correlation lab's output, the native run's results
  (`native_ch06.json`) and the FS-11 lab's bundles.

## Chapter 7: Safe Telemetry: Privacy-Aware Observability by Design

- Command: `make verify-ch07` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages); `tests/lab` needs
  the `lab` group
- Date: 2026-10-07

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L07-01 | Redaction of one value | `src/wrenholt/privacy/redact.py` | `tests/privacy/test_vault_and_redact.py`, `tests/privacy/test_privacy_scan.py` | pass | pending |
| L07-02 | The span redactor | `src/wrenholt/privacy/redact.py` | `tests/privacy/test_vault_and_redact.py` (attributes set after start) | pass | pending |
| L07-03 | The vault's audited read | `src/wrenholt/privacy/vault.py` | `tests/privacy/test_vault_and_redact.py` | pass | pending |
| L07-04 | Collector redaction | `deploy/compose/otelcol/config.yaml` | `tests/unit/test_config_lint.py`; `otelcol-contrib validate`; native run | pass | pending |
| L07-05 | FS-14 lab | `scripts/fs14_pii.py` | run command (2026-10-07 12:10 UTC); `tests/privacy/test_privacy_scan.py` | pass (SIMULATED workload) | pending |
| L07-06 | Hash lab | `scripts/hash_reversal.py` | run command (12:23 UTC); `tests/privacy/test_classify_and_pseudonym.py` | pass; timings vary by machine | pending |
| L07-07 | Privacy scan test | `tests/privacy/test_privacy_scan.py` | itself | pass | pending |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience tests/drift
  tests/privacy`: 110 passed, 4 skipped (no `promtool` on `PATH`;
  `SEMCONV_GENAI_DIR` unset). With `promtool` and the pinned checkout
  the drift suite: 17 passed. `pytest tests/lab`: 8 passed. 122 tests:
  unit 67, slo 15, resilience 3, drift 17, lab 8, privacy 12.
- `ruff check`, `ruff format --check` and `mypy --strict` with the
  lab group (111 source files): clean. `uv lock --check`: 96 packages.
  `docker compose config`: valid. `otelcol-contrib validate` on the
  Collector configuration: valid with a 41-byte key; it rejected the
  first, 22-byte development key.
- Every source listing in Chapters 1 to 7 is verbatim in the
  repository (L05-01 as a verbatim prefix, as since Chapter 6).
- The first privacy scan found order IDs in `url.path` on the orders
  service's server spans: the ASGI instrumentation sets it after the
  span starts. The span redactor now wraps the span's attribute
  setters; the scan then found none.
- Native run, 2026-10-07 12:19 UTC: Collector 0.162.0 with the
  redaction processor, Tempo 3.1.0 and Loki 3.7.8; Linnet as the FS-14
  leaky app, without in-process redaction. Loki stored the debug lines
  with emails replaced by a 64-hex HMAC and
  `redaction_body_masked_count` 1; names unchanged. Tempo, fetched by
  the trace IDs on those log lines: 2 traces, 0 raw order IDs, 0
  emails; the client span's `url.full` hashed with
  `redaction.masked.count` 1; the orders service's `url.path` arrived
  pseudonymised in-process.
- Read 2026-10-06 and 07: OpenTelemetry's guidance on sensitive data;
  OWASP LLM02:2025; NIST AI 600-1 (official PDF); the redaction
  processor's README and metadata at v0.162.0; the GenAI spans
  document at `bcc7f9c` on content capture and external storage.
- Figure 7.1 and Table 7.1 are drawn by `figures_ch07.py` from the
  contract module and the native run's results (`native_ch07.json`).

## Chapter 8: Streaming and Asynchronous Workloads

- Command: `make verify-ch08` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages); `tests/lab` needs
  the `lab` group
- Date: 2026-10-08

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L08-01 | The stream clock | `src/wrenholt/gateway/streaming.py` | `tests/unit/test_stream_clock.py`, `tests/unit/test_streaming.py` | pass | pending |
| L08-02 | Reading an attempt | `src/wrenholt/gateway/client.py` | `tests/unit/test_streaming.py`, `tests/unit/test_stream_context.py` | pass | pending |
| L08-03 | Ending an attempt | `src/wrenholt/gateway/client.py` | `tests/unit/test_streaming.py`; FS-04 lab | pass | pending |
| L08-04 | The status code waits for the first chunk | `src/wrenholt/api/app.py` | `tests/unit/test_sse_api.py` (a 503 before the stream) | pass | pending |
| L08-05 | The server-sent events relay | `src/wrenholt/api/app.py` | `tests/unit/test_sse_api.py`; FS-04 lab | pass | pending |
| L08-06 | The `ttfc` SLI query | `deploy/compose/grafana/provisioning/dashboards/llm-gateway.json` (the same expression on one line) | `promtool check rules` on the wrapped listing; `tests/drift/test_dashboard_lint.py`; native run | pass | pending |
| L08-07 | FS-02 lab | `scripts/fs02_brownout.py` | run command (2026-10-08 15:01 UTC) | pass (SIMULATED); timings vary by machine | pending |
| L08-08 | FS-04 lab | `scripts/fs04_stream_cut.py` | run command (15:15 UTC, identical to the 14:32 run); `tests/unit/test_sse_api.py` | pass (SIMULATED) | pending |
| L08-09 | A cut before the first chunk is retried | `tests/unit/test_streaming.py` | itself | pass | pending |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience tests/drift
  tests/privacy` with `promtool` on `PATH` and `SEMCONV_GENAI_DIR`
  set: 136 passed. `pytest tests/lab`: 8 passed. 144 tests: unit 88,
  slo 15, resilience 3, drift 17, lab 8, privacy 13.
- `ruff check`, `ruff format --check` and `mypy --strict` with the
  lab group (121 source files): clean. `uv lock --check`: 96 packages.
  `otelcol-contrib validate` (0.162.0): valid. The Compose files parse
  and pass the config lint; `docker compose config` was not run here
  (no Docker), and the compose-smoke workflow runs it on push.
- Every source listing in Chapters 1 to 8 is verbatim in the
  repository (42 checked; 16 captured outputs and queries skipped).
  Earlier labs rerun on the Chapter 8 code: FS-09, the names lab,
  FS-11 and FS-14 (which gained a streamed option) print their
  listings unchanged; FS-01, the gateway lab and the correlation lab
  differ only in timings, trace IDs and `service.version` (ch08).
- The rename drill now reports three problems: the unknown name,
  then one missing label for each of the two panels that group by
  provider. Its test asserts the unknown name first and a label
  problem for every panel after it. L05-04 stays the Chapter 5
  capture, which showed two.
- Native run, 2026-10-08 14:47 UTC: Collector 0.162.0, Prometheus
  3.15.0 (OTLP receiver, exemplar storage), Tempo 3.1.0 and Loki
  3.7.8; Linnet streaming against the mock, one warm-up answer, ten
  steady and ten during `MOCK_LLM_PLAN=fs02`, ten at a time. The
  first-chunk histogram's `le` labels included `2.5`, `2.56` and `4`;
  the 2.5 s bucket held 11 of 21; the SLI panel read 0.5 (0.0 on a
  first attempt without the warm-up: `increase()` cannot count a new
  series' first sample); the p95 panel read 3.86 s for
  `wrenholt.mock_a` against a 3.0 s scheduled wait. Details:
  `native_ch08.json` in the figures archive.
- Read 2026-10-08: the Claude API errors page (errors after HTTP 200)
  and the Claude streaming page (error events, `ping` events); the
  GenAI metrics document at `bcc7f9c`; installed sources of openai
  3.22.1 (`_streaming.py`), Starlette 1.7.0 (`responses.py`) and
  uvicorn 0.54.0 (`protocols/http`).
- Figure 8.1 is drawn by `figures_ch08.py` from a timeline measured
  at the gateway against the mock's schedules (`timeline_ch08.json`,
  14:51 UTC). Table 8.1 follows the compatibility module and the
  pinned GenAI metrics document.

## Chapter 9: Observing Retrieval, Tools and Agent Loops

- Command: `make verify-ch09` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages); `tests/lab` needs
  the `lab` group
- Date: 2026-10-12

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L09-01 | The retrieval span | `src/wrenholt/rag/retriever.py` | `tests/unit/test_retrieval.py` (attributes without text; FS-08); drift suite; native run | pass | pending |
| L09-02 | The start-up check | `src/wrenholt/rag/retriever.py` | `tests/unit/test_retrieval.py`; native run (a second API process refused the re-indexed build) | pass | pending |
| L09-03 | The loop guard | `src/wrenholt/orchestrator/guard.py` | `tests/unit/test_loop_guard.py` | pass | pending |
| L09-04 | The tool loop | `src/wrenholt/orchestrator/linnet.py` | `tests/unit/test_agent.py`, `tests/unit/test_loop_guard.py` | pass | pending |
| L09-05 | One span per tool call | `src/wrenholt/tools/toolbox.py` | `tests/unit/test_idempotent_refund.py` (invalid arguments), `tests/privacy/test_privacy_scan.py` | pass | pending |
| L09-06 | The idempotent refund | `src/wrenholt/tools/toolbox.py` | `tests/unit/test_idempotent_refund.py`; FS-07 lab; native run | pass | pending |
| L09-07 | Retrieval and agent queries | `deploy/compose/grafana/provisioning/dashboards/llm-gateway.json` (the same expressions on one line) | `promtool check rules` on the two wrapped PromQL expressions; the TraceQL query equals the replay panel's; `tests/drift/test_dashboard_lint.py`; native run | pass | pending |
| L09-08 | FS-06 lab | `scripts/fs06_tool_loop.py` | run command (2026-10-12 08:13 UTC; rerun at 16:30 UTC differs only in the 1.44 s timing, then 1.28 s); `tests/unit/test_loop_guard.py` | pass (SIMULATED); timings vary by machine | pending |
| L09-09 | FS-07 lab | `scripts/fs07_duplicate_refund.py` | run command (08:13 UTC; identical at 16:30 UTC); `tests/unit/test_idempotent_refund.py` | pass (SIMULATED) | pending |
| L09-10 | FS-08 lab | `scripts/fs08_empty_retrieval.py` | run command (08:13 UTC; identical at 16:30 UTC); `tests/unit/test_retrieval.py` | pass (SIMULATED) | pending |
| L09-11 | FS-07 tests | `tests/unit/test_idempotent_refund.py` | itself | pass | pending |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience tests/drift
  tests/privacy` with `promtool` on `PATH` and `SEMCONV_GENAI_DIR`
  set: 164 passed. `pytest tests/lab`: 8 passed. 172 tests: unit 113,
  slo 17, resilience 3, drift 17, lab 8, privacy 14.
- `ruff check`, `ruff format --check` and `mypy --strict` with the
  lab group (144 source files): clean. `uv lock --check`: 96 packages.
  `otelcol-contrib validate` (0.162.0) with the Compose environment:
  valid. `docker compose config` was not run here (no Docker); the
  compose-smoke workflow runs it on push.
- Every source listing in Chapters 1 to 9 is verbatim in the
  repository (49 checked; 20 captured outputs and queries skipped).
- Earlier tests changed with the agent: the correlation test now
  expects three provider requests for an order question (two
  decisions and the answer) and checks each; the orders-service rule
  that a new key cannot refund an order twice became a test of
  refunds item by item (a second key refunds another part, 201 and
  `part_refunded`; more than is left gets 422; the rest refunds the
  order in full; a refund after that gets 409); the FS-14 lab app
  subclasses `Linnet`; the rename
  drill skips panels whose series the gateway does not produce. The
  drift fixture runs the agent (a policy question and a refund
  against the orders service), and the privacy scan gained a test
  that its tools ran and leaked nothing.
- Earlier labs rerun on the Chapter 9 code (16:30 UTC): FS-09, the
  names lab, FS-11, FS-14 and FS-04 print their listings unchanged;
  FS-01, the outage lab, the gateway lab, the hash lab and FS-02
  differ only in timings (the outage lab's SDK warning counts, 18 and
  13 against 17 and 12, follow its timings). The correlation lab now
  reports 17 spans where L06-04 shows 6, with a new trace ID and
  `service.version` ch09: the agent adds `invoke_agent`, retrieval,
  embeddings, build context, two deciding model calls (chat, attempt
  and HTTP each) and an `execute_tool` span around the orders call.
  L06-04 stays the Chapter 6 capture, as L05-04 stays Chapter 5's
  (the rename drill reports three problems, as in Chapter 8).
- Native run, 2026-10-12 08:05 UTC: Collector 0.162.0, Prometheus
  3.15.0 (OTLP receiver, exemplar storage), Tempo 3.1.0 and Loki
  3.7.8; Linnet with the orders service (`ORDERS_SLOW_COMMIT_MS=2500`)
  and the mock. Twenty questions, all answered with 200: 11 that
  named no order (4 streamed), 4 order lookups and 2 refunds (1
  streamed), then 3 order lookups after restarting the mock with
  `MOCK_LLM_PLAN=fs06`. Raw counters: stop reasons `no_tools` 11,
  `finished` 6, `repeated_call` 3; `wrenholt_retrieval_returned`
  buckets `le="0"` 0, `"1"` 3, `"2"` 16, `"3"` 20; operation-duration
  counts chat 40, retrieval 20, embeddings 20. The stop-reason panel
  read 0 for `repeated_call` (`increase()` cannot count a new series'
  first sample). A refund's trace: the orders service answered the
  first `POST /refunds` with 201 after 2,501.94 ms, Linnet's client
  span ended with `ReadTimeout` at 2,006.58 ms, and the retry's server
  span answered 200 in 2.79 ms; the tool span carried
  `wrenholt.tool.replayed` true. Tempo returned
  `gen_ai.retrieval.documents` as an array of key-value lists. TraceQL
  found 2 traces with replayed refunds and 3 with `repeated_call`; in
  a first run, search returned nothing for traces that could already
  be fetched by ID, so the second run fetched by ID first. A second API
  process started with `WRENHOLT_INDEX_EMBEDDER=wrenholt-embed-2`
  exited with code 1 and the `IndexMismatch` message. Details:
  `native_ch09.json` in the figures archive.
- Read 2026-10-12: the GenAI spans, agent spans and metrics documents
  at `bcc7f9c` and the retrieval-documents JSON Schema; MAST (Cemri et
  al., arXiv 2503.13657v3, Appendix A.1); Barnett et al. (CAIN 2024,
  arXiv 2401.05856v1, FP3); the AWS Builders' Library article on
  idempotent APIs; draft-ietf-httpapi-idempotency-key-header-07
  (expired 18 April 2026); installed sources of openai 3.22.1 (the
  function-call `arguments` docstring), opentelemetry-api 1.45.0
  (`AnyValue`) and Starlette 1.7.0 (`BaseHTTPMiddleware` body cache).
- Figure 9.1 is drawn by `figures_ch09.py` from a policy question's
  trace in the native run (`traces_ch09.json`). Figure 9.2, a diagram
  of the guard's checks, and Table 9.1 come from the same script;
  the table takes each name's source from the compatibility module
  and its data class from the privacy contract.
