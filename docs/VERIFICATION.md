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
| L01-01 | FS-01 fault plan | `services/mock_llm/faults.py` | `tests/unit/test_mock_provider.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L01-02 | Mock provider fault injection and request log | `services/mock_llm/app.py` | `tests/unit/test_mock_provider.py`, `tests/unit/test_baseline_smoke.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L01-03 | Linnet baseline answer path (SDK defaults) | `src/wrenholt/orchestrator/baseline.py` | `tests/unit/test_baseline_smoke.py`, `tests/unit/test_retry_layers_multiply.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L01-04 | Layered default instrumentation | `src/wrenholt/labs/layered.py` | `tests/lab/test_fs01_hidden_retry.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L01-05 | FS-01 lab output | `scripts/fs01_hidden_retry.py` | run command; output matches the listing except millisecond timings | pass (SIMULATED) | pass: output re-run 20 Oct 2026, only timings differ |
| L01-06 | Manual three-terminal run | `services/mock_llm/main.py`, `src/wrenholt/api/main.py` | executed as printed; reply in about 2 s; mock log 429, 429, 200 with retry counts 0, 1, 2 | pass (SIMULATED) | not re-run: needs two terminals and a running provider |
| L01-07 | Blind-spot test | `tests/lab/test_fs01_hidden_retry.py` | itself (2 tests) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |

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
| L02-01 | Request map: deadline, budgets, dependencies | `src/wrenholt/slo/request_map.yaml` | `tests/slo/test_catalog_and_map.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L02-02 | SLI catalog entries | `src/wrenholt/slo/sli_catalog.yaml` | `tests/slo/test_catalog_and_map.py`, `tests/slo/test_sli_calculators.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L02-03 | `SliResult` and the low-traffic guard | `src/wrenholt/slo/sli.py` | `tests/slo/test_sli_calculators.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L02-04 | Rules and counting | `src/wrenholt/slo/sli.py` | `tests/slo/test_sli_calculators.py`, `tests/slo/test_fs09_slis.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L02-05 | FS-09 SLI report | `scripts/fs09_sli_report.py` | run command; output identical to the listing | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |
| L02-06 | FS-09 worked numbers | `tests/slo/test_fs09_slis.py` | itself | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |

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
| L03-01 | `linnet-api` service | `deploy/compose/docker-compose.yml` | `tests/unit/test_config_lint.py`; `docker compose config` (v5.5.1); native run of checks 10-17 | pass; Compose run in CI pending the push | pass: ran in CI run 39411828181 (checks 10-15) |
| L03-02 | `start_telemetry()` | `src/wrenholt/telemetry/setup.py` | `tests/unit/test_telemetry_setup.py`, `tests/resilience/test_collector_outage.py`; native run | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L03-03 | Lifespan flush | `src/wrenholt/telemetry/setup.py` | `tests/resilience/test_collector_outage.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L03-04 | FastAPI's built-in telemetry off | `src/wrenholt/telemetry/framework.py` | `tests/unit/test_telemetry_setup.py`; single-request probe: 1 span per request (2 before) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L03-05 | Collector outage lab | `scripts/collector_outage.py` | run command; output identical to the listing | pass (workload SIMULATED; SDK behaviour measured) | pass: output re-run 20 Oct 2026, only timings differ |
| L03-06 | CI checks 16-17 | `.github/workflows/compose-smoke.yml` | workflow parses; same checks run natively against the real Collector | pass natively; CI run pending the push | pass: CI run 39411828181 (checks 16-17) |
| L03-07 | Uvicorn and the flush | `tests/resilience/test_collector_outage.py` | itself | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L03-08 | Config lint rules | `tests/unit/test_config_lint.py` | itself | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |

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
| L04-01 | Closed `error.type` set and retry rules | `src/wrenholt/gateway/errors.py` | `tests/unit/test_error_map.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L04-02 | OpenAI-compatible classifier | `src/wrenholt/gateway/openai_compat.py` | `tests/unit/test_error_map.py` (19 cases) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L04-03 | Retry policy | `src/wrenholt/gateway/policy.py` | `tests/unit/test_error_map.py`, `tests/unit/test_gateway_contract.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L04-04 | Request span and retry loop | `src/wrenholt/gateway/client.py` | `tests/unit/test_gateway_contract.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L04-05 | Attempt span on failure and success | `src/wrenholt/gateway/client.py` | `tests/unit/test_gateway_contract.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L04-06 | Gateway comparison lab | `scripts/gateway_lab.py` | run command (2026-10-06 02:51 UTC); `tests/lab/test_gateway_comparison.py` | pass (SIMULATED); counts identical on re-run, timings vary by milliseconds | pass: output re-run 20 Oct 2026, only timings differ |
| L04-07 | FS-18 contract test | `tests/unit/test_gateway_contract.py` | itself | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L04-08 | Prometheus and TraceQL queries | none (queries) | native run, 2026-10-06 02:56 UTC | pass natively; Compose run pending the push | not re-run: needs a running stack with data |

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
| L05-01 | The registry | `src/wrenholt/telemetry/conventions.py` | `tests/drift/test_conventions_drift.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L05-02 | Snapshot check | `src/wrenholt/telemetry/drift.py` | `tests/drift/test_conventions_drift.py`, `tests/drift/test_rename_drill.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L05-03 | Names lab | `scripts/names_lab.py` | run command (2026-10-06 08:17 UTC; identical at 08:55); `tests/lab/test_names_lab.py` | pass (SIMULATED workload) | pass: output re-run 20 Oct 2026, identical |
| L05-04 | Rename drill | `scripts/rename_drill.py` | run command (08:17 UTC; identical at 08:55); `tests/drift/test_rename_drill.py` | pass (SIMULATED workload) | differs: re-run 20 Oct 2026 finds 3 drift problems, the listing 2 (decision needed) |
| L05-05 | Drift tests | `tests/drift/test_conventions_drift.py` | itself | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L05-06 | CI drift step | `.github/workflows/compose-smoke.yml` | workflow parses; the same suite run locally with `promtool` and the checkout: 17 passed | pass locally; CI run pending the push | pass: CI run 39411828181 (drift suite, pinned checkout) |

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
| L06-01 | Trace-context-only propagation | `src/wrenholt/telemetry/setup.py` | `tests/unit/test_correlation.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L06-02 | The model pin check | `src/wrenholt/gateway/client.py` | `tests/unit/test_fs11.py`; drift suite | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L06-03 | Recording the bundle off the request path | `src/wrenholt/repro.py` | `tests/unit/test_correlation.py`, `tests/unit/test_repro.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L06-04 | Correlation lab | `scripts/correlation_lab.py` | run command (2026-10-06 09:10 UTC); `tests/unit/test_correlation.py` | pass (SIMULATED workload); IDs differ per run | pass: output re-run 20 Oct 2026, only random trace IDs differ |
| L06-05 | FS-11 lab | `scripts/fs11_model_change.py` | run command (14:58 UTC); `tests/unit/test_fs11.py` | pass (SIMULATED workload) | pass: output re-run 20 Oct 2026, identical |
| L06-06 | Correlation test | `tests/unit/test_correlation.py` | itself | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L06-07 | Exemplar, trace and log queries | none (queries) | native run, 2026-10-06 14:53 UTC | pass natively; Compose run pending the push | not re-run: needs a running stack with data |

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
| L07-01 | Redaction of one value | `src/wrenholt/privacy/redact.py` | `tests/privacy/test_vault_and_redact.py`, `tests/privacy/test_privacy_scan.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L07-02 | The span redactor | `src/wrenholt/privacy/redact.py` | `tests/privacy/test_vault_and_redact.py` (attributes set after start) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L07-03 | The vault's audited read | `src/wrenholt/privacy/vault.py` | `tests/privacy/test_vault_and_redact.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L07-04 | Collector redaction | `deploy/compose/otelcol/config.yaml` | `tests/unit/test_config_lint.py`; `otelcol-contrib validate`; native run | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L07-05 | FS-14 lab | `scripts/fs14_pii.py` | run command (2026-10-07 12:10 UTC); `tests/privacy/test_privacy_scan.py` | pass (SIMULATED workload) | pass: output re-run 20 Oct 2026, identical |
| L07-06 | Hash lab | `scripts/hash_reversal.py` | run command (12:23 UTC); `tests/privacy/test_classify_and_pseudonym.py` | pass; timings vary by machine | pass: output re-run 20 Oct 2026, only timings differ |
| L07-07 | Privacy scan test | `tests/privacy/test_privacy_scan.py` | itself | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |

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
| L08-01 | The stream clock | `src/wrenholt/gateway/streaming.py` | `tests/unit/test_stream_clock.py`, `tests/unit/test_streaming.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L08-02 | Reading an attempt | `src/wrenholt/gateway/client.py` | `tests/unit/test_streaming.py`, `tests/unit/test_stream_context.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L08-03 | Ending an attempt | `src/wrenholt/gateway/client.py` | `tests/unit/test_streaming.py`; FS-04 lab | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L08-04 | The status code waits for the first chunk | `src/wrenholt/api/app.py` | `tests/unit/test_sse_api.py` (a 503 before the stream) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L08-05 | The server-sent events relay | `src/wrenholt/api/app.py` | `tests/unit/test_sse_api.py`; FS-04 lab | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L08-06 | The `ttfc` SLI query | `deploy/compose/grafana/provisioning/dashboards/llm-gateway.json` (the same expression on one line) | `promtool check rules` on the wrapped listing; `tests/drift/test_dashboard_lint.py`; native run | pass | not re-run: needs a running stack with data |
| L08-07 | FS-02 lab | `scripts/fs02_brownout.py` | run command (2026-10-08 15:01 UTC) | pass (SIMULATED); timings vary by machine | pass: output re-run 20 Oct 2026, only timings differ |
| L08-08 | FS-04 lab | `scripts/fs04_stream_cut.py` | run command (15:15 UTC, identical to the 14:32 run); `tests/unit/test_sse_api.py` | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |
| L08-09 | A cut before the first chunk is retried | `tests/unit/test_streaming.py` | itself | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |

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
| L09-01 | The retrieval span | `src/wrenholt/rag/retriever.py` | `tests/unit/test_retrieval.py` (attributes without text; FS-08); drift suite; native run | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L09-02 | The start-up check | `src/wrenholt/rag/retriever.py` | `tests/unit/test_retrieval.py`; native run (a second API process refused the re-indexed build) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L09-03 | The loop guard | `src/wrenholt/orchestrator/guard.py` | `tests/unit/test_loop_guard.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L09-04 | The tool loop | `src/wrenholt/orchestrator/linnet.py` | `tests/unit/test_agent.py`, `tests/unit/test_loop_guard.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L09-05 | One span per tool call | `src/wrenholt/tools/toolbox.py` | `tests/unit/test_idempotent_refund.py` (invalid arguments), `tests/privacy/test_privacy_scan.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L09-06 | The idempotent refund | `src/wrenholt/tools/toolbox.py` | `tests/unit/test_idempotent_refund.py`; FS-07 lab; native run | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L09-07 | Retrieval and agent queries | `deploy/compose/grafana/provisioning/dashboards/llm-gateway.json` (the same expressions on one line) | `promtool check rules` on the two wrapped PromQL expressions; the TraceQL query equals the replay panel's; `tests/drift/test_dashboard_lint.py`; native run | pass | not re-run: needs a running stack with data |
| L09-08 | FS-06 lab | `scripts/fs06_tool_loop.py` | run command (2026-10-12 08:13 UTC; rerun at 16:30 UTC differs only in the 1.44 s timing, then 1.28 s); `tests/unit/test_loop_guard.py` | pass (SIMULATED); timings vary by machine | pass: output re-run 20 Oct 2026, only timings differ |
| L09-09 | FS-07 lab | `scripts/fs07_duplicate_refund.py` | run command (08:13 UTC; identical at 16:30 UTC); `tests/unit/test_idempotent_refund.py` | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |
| L09-10 | FS-08 lab | `scripts/fs08_empty_retrieval.py` | run command (08:13 UTC; identical at 16:30 UTC); `tests/unit/test_retrieval.py` | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |
| L09-11 | FS-07 tests | `tests/unit/test_idempotent_refund.py` | itself | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |

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

## Chapter 10: Metrics, Cardinality and the Telemetry Pipeline

- Command: `make verify-ch10` (or the commands under that target);
  `scripts/fetch_collector.sh` installs the pinned Collector first
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages); `tests/lab` needs
  the `lab` group; the Collector labs need otelcol-contrib 0.162.0
- Date: 2026-10-13

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L10-01 | Tail sampling | `deploy/compose/otelcol/config.production.yaml` | `tests/unit/test_pipeline_config.py` (policies against `sampling.POLICIES`, thresholds, sizing); `otelcol-contrib validate`; FS-15 lab; native runs | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L10-02 | The coverage map | `src/wrenholt/telemetry/sampling.py` | `tests/unit/test_pipeline_config.py` (every gateway panel names a policy) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L10-03 | Export queues | `deploy/compose/otelcol/config.production.yaml` | `tests/unit/test_pipeline_config.py` (the queues hold what the comment says); native run (capacity reported in items) | pass | superseded by L11-08 (approved) |
| L10-04 | The budget | `src/wrenholt/telemetry/conventions.py` | `tests/unit/test_cardinality.py`; `tests/drift/test_budget_drift.py`; native run (221 series, none outside the budget) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L10-05 | The guard | `src/wrenholt/telemetry/budget.py` | `tests/unit/test_cardinality.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L10-06 | The first tier | `deploy/compose/otelcol/loadbalancing.yaml` | `otelcol-contrib validate`; `tests/unit/test_pipeline_config.py`; not run (decisions 4 and 8) | pass (validated) | pass: native load-balancing exercise, 20 Oct 2026 |
| L10-07 | Pipeline queries | `deploy/compose/grafana/provisioning/dashboards/telemetry-pipeline.json` (the same expressions on one line) | `promtool check rules` on the four wrapped expressions; `tests/drift/test_dashboard_lint.py`; native run | pass | not re-run: needs a running stack with data |
| L10-08 | FS-15 lab | `scripts/fs15_sampling_blind_spot.py` | run command (2026-10-13 03:17 UTC, identical to the earlier run); `tests/resilience/test_collector_pipeline.py` asserts every line | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |
| L10-09 | Collector overload lab | `scripts/collector_overload.py` | run command (2026-10-13 04:11 UTC); `tests/resilience/test_collector_pipeline.py` asserts the counts | pass (SIMULATED); waiting times vary | pass: output re-run 20 Oct 2026, only timings differ |
| L10-10 | Sizing tests | `tests/unit/test_pipeline_config.py` | itself | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience tests/drift
  tests/privacy` with `.native/bin` (otelcol-contrib, promtool) on
  `PATH` and `SEMCONV_GENAI_DIR` set: 198 passed. `pytest tests/lab`:
  8 passed. 206 tests: unit 141, slo 17, resilience 5, drift 21,
  lab 8, privacy 14. Without the Collector, four skip.
- `ruff check`, `ruff format --check` and `mypy --strict` with the
  lab group (155 source files): clean. `uv lock --check`: 96 packages.
  `otelcol-contrib validate` accepted `config.yaml`,
  `config.production.yaml` and `loadbalancing.yaml`. `docker compose
  config` was not run here (no Docker), so the production override
  is checked only by `tests/unit/test_pipeline_config.py`.
- Every source listing in Chapters 1 to 10 is verbatim in the
  repository (56 checked; 23 captured outputs and queries skipped).
- L08-02 changed with the author's approval (13 Oct 2026, decision
  60): the stream reader passes `record_exception=False` and
  `set_status_on_exception=False` to `use_span`, because
  `StopAsyncIteration` ended every completed attempt as ERROR. The
  new `test_a_completed_attempt_is_not_an_error` fails without the
  change. The Chapter 8 doc's listing and paragraph were updated, and
  the check above uses the new L08-02.
- Earlier tests changed: the dashboard lint and the rename drill take
  the Collector snapshot, so the pipeline dashboard's names are known;
  the drift fixture is unchanged and now also feeds the budget test.
  Running `tests/lab` and the unit tests in one process fails eleven
  streaming tests: opentelemetry-instrumentation-openai-v2 2.4b0 wraps
  a stream in an object whose `close()` is synchronous, so Wrenholt's
  `await events.close()` fails while that instrumentation is active.
  The verify targets have run `tests/lab` in its own process since
  Chapter 3.
- Earlier labs rerun on the Chapter 10 code (04:27 UTC): FS-04, FS-07,
  FS-08, FS-09, FS-11, FS-14, the names lab and the rename drill print
  their outputs unchanged (the rename drill still reports three
  problems, as in Chapters 8 and 9; L05-04 shows Chapter 5's two).
  FS-01, FS-02, FS-06, the gateway lab, the hash lab and the outage
  lab differ only in timings (the outage lab's SDK warnings, 17 and
  12, follow its timings). The correlation lab differs in trace IDs
  and `service.version` ch10.
- Native runs, 2026-10-13 03:35, 03:58 and 04:07 UTC: Collector
  0.162.0 with `config.production.yaml` and `GOMEMLIMIT=320MiB`,
  Prometheus 3.15.0 (OTLP receiver, exemplar storage, Collector
  scraped every 5 s), Tempo 3.1.0 and Loki 3.7.8; Linnet, the orders
  service and the mock. Each run sent 33 answers: a warm-up; 6 policy
  answers, 3 order lookups, 3 refunds and 3 streamed answers with
  nothing wrong; then 8 policy answers under `MOCK_LLM_PLAN=fs15`, 3
  streamed under `fs02`, 3 under `fs11`, 2 order lookups under
  `fs06`, and a refund with `ORDERS_SLOW_COMMIT_MS=2500`. Per answer:
  2 traces in every journey (the request and the reproduction
  bundle) and 9, 18, 24 and 9 spans for policy, order, refund and
  streamed answers; 2 log records. Kept by the production profile:
  all 11 quiet failures in every run; healthy answers 2, 2 and 1 of
  22; in the second run 15 of 66 traces, votes baseline 5, errors 3,
  slow-first-chunk 3, model-mismatch 3, loop-stopped 2,
  replayed-write 1, none dropped too early. Exemplars (second run):
  155 pointing at 23 traces; all 9 quiet-failure traces resolved, 13
  of 14 healthy ones did not. Prometheus stored 221 Wrenholt series,
  each metric within its budget and none outside it; the Collector's
  45 metric names as exposed, without `_total`. Collector memory:
  RSS 212 MB, Go heap 31 MB. Every pipeline panel returned data except
  the two failure panels. Tempo answered 200 with no spans for traces
  it never stored, so the runs counted spans. The first run used the
  traces queue of 30,000 the profile had before its final sizing; the
  sampling settings were the same in all three. Details:
  `native_ch10_*.json` in the figures archive.
- Failure capture, 2026-10-13 03:47 UTC: the production profile with
  every backend at an unreachable address, queues of 200 items and
  retries ending after 3 s, fed traces, metrics and logs from the
  Python SDK; Prometheus stored the six failure counters
  (`otelcol_exporter_enqueue_failed_*`, `otelcol_exporter_send_failed_*`)
  that complete `src/wrenholt/telemetry/otelcol_snapshot.json` (51
  names). With queues of 5 items every request was refused at once
  ("element size too large").
- NHCB check, 2026-10-13: two Prometheus 3.15.0 instances, one with
  `otlp.convert_histograms_to_nhcb: true`, received the same
  time-to-first-chunk histogram for two routes: 38 series against 2;
  the `le="2.5"` ratio returned nothing on the converted copy;
  `histogram_fraction(0, 2.5, ...)` and the classic ratio both
  returned 0.75; the p95s matched (3.712 s).
- `scripts/fetch_collector.sh`: the four archives were streamed from
  the v0.162.0 release to record their SHA-256; the script installed
  a binary byte-identical to `.native/bin/otelcol-contrib`, and a
  copy with an altered hash refused the archive and installed nothing.
- Read 2026-10-13 at the v0.162.0 tags: the tail sampling processor
  (README, metadata, documentation, `numeric_tag_filter.go`), the
  exporter helper (README, metadata), the memory limiter, batch
  processor, otlp_http and load-balancing exporter READMEs, and the
  core CHANGELOG (the `otlp_http` rename in v0.146.0); Prometheus
  v3.15.0 configuration docs; installed sources of opentelemetry-sdk
  1.45.0 (Views, `BatchSpanProcessor`), opentelemetry-api 1.45.0
  (`use_span`) and opentelemetry-instrumentation-openai-v2 2.4b0.
- Figures 10.1 and 10.2 are diagrams drawn by `figures_ch10.py`, which
  also builds Table 10.1 from `otelcol-contrib components` and Table
  10.2 from `conventions.BUDGET`.

## Chapter 11: Tokens, Cost and Latency Economics

- Command: `make verify-ch11` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages)
- Date: 2026-10-13

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L11-01 | The price table | `src/wrenholt/gateway/prices.yaml` | `tests/unit/test_cost.py` (every routed model priced; a table that looks wrong refused) | pass (SIMULATED prices) | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L11-02 | One call's cost | `src/wrenholt/gateway/cost.py` | `tests/unit/test_cost.py` (the policy answer by hand, cached rate, five times on the large model) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L11-03 | Recording a call | `src/wrenholt/gateway/cost.py` | `tests/unit/test_cost.py`; `tests/drift` (every emitted key in its budget) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L11-04 | Charging a call | `src/wrenholt/gateway/client.py` | `tests/unit/test_cost.py` (whole and streamed calls charged, a cut stream not) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L11-05 | The ledger | `src/wrenholt/gateway/limits.py` | `tests/unit/test_limits.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L11-06 | Refused at the limit | `src/wrenholt/api/app.py` | `tests/unit/test_limits.py` (429 with `Retry-After`); native run | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L11-07 | Chapter 11's budget | `src/wrenholt/telemetry/conventions.py` | `tests/unit/test_cardinality.py` (combinations from the code; 1,955 of 2,000) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L11-08 | The metrics queue | `deploy/compose/otelcol/config.production.yaml` | `tests/unit/test_pipeline_config.py` (187 points × 60 exports); `otelcol-contrib validate` | pass | superseded by L13-08 (approved) |
| L11-09 | Two dashboard queries | `deploy/compose/grafana/provisioning/dashboards/cost.json` (the same expressions on one line) | `promtool check rules` on every dashboard expression; `tests/drift/test_dashboard_lint.py`; native run | pass | not re-run: needs a running stack with data |
| L11-10 | FS-12 lab | `scripts/fs12_token_explosion.py` | run command (2026-10-13); `tests/unit/test_economics.py` asserts every number | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |
| L11-11 | FS-13 lab | `scripts/fs13_costly_fallback.py` | run command (2026-10-13); `tests/unit/test_economics.py` asserts every number | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |
| L11-12 | The normal hour by hand | `tests/unit/test_economics.py` | itself | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience tests/drift
  tests/privacy` with `.native/bin` (otelcol-contrib, promtool) on
  `PATH`: 227 passed, 1 skipped (`SEMCONV_GENAI_DIR` not set; with
  it, the drift suite's snapshot check passes too). `pytest tests/lab`:
  8 passed. 236 tests: unit 171, slo 17, resilience 5, drift 21,
  lab 8, privacy 14. Thirty are new.
- `ruff check`, `ruff format --check` and `mypy --strict` (167 source
  files): clean. `uv lock --check`: 96 packages.
- Every source listing in Chapters 1 to 11 is in the repository (65
  checked; 26 captured outputs and queries skipped), except L10-03,
  which `tools/check_listings.py` reports as superseded by L11-08: the
  metrics queue grew from 10,000 to 12,000 because Chapter 11's
  metrics take an instance from 151 to 187 points an export. This
  needs the author's approval, as L08-02 did.
- Chapter 10's tests changed with the budget: the worked numbers of
  Table 10.2 are asserted over Chapter 10's eleven metrics, and the
  queue test over all of them. The drift run now gives every gateway
  prices, a cap and a ledger, includes one refused call, and counts
  registered keys that appear only on metrics
  (`gen_ai.token.modality`).
- Native run, 2026-10-13 10:43:52 UTC, 37 s: Collector 0.162.0 with
  the production profile, Prometheus 3.15.0, Tempo, Loki, Linnet,
  orders and the mock as local processes, limit $0.001 an hour.
  18 answers: 9 answered, 9 refused with 429; recorded spend
  $0.0010228. Prometheus stored `wrenholt_gateway_cost_total`,
  `wrenholt_gateway_limited_total`, `wrenholt_gateway_spend_limit`
  and the token metrics, with labels `wrenholt_tenant`,
  `gen_ai_prompt_version` and `gen_ai_token_modality`; all nine
  panels of the tokens and cost dashboard returned data. An earlier
  run that morning found no `wrenholt_gateway_spend_limit`: a synchronous
  gauge set while the API was built, before telemetry started, was
  lost. The gauge is now observed at every export.
- Sources read: semantic-conventions-genai at `bcc7f9c`
  (`model/gen-ai/token-metrics.yaml`,
  `docs/gen-ai/gen-ai-token-metrics.md`,
  `docs/gen-ai/non-normative/token-metrics-design.md`); OWASP
  LLM10:2025 (raw file fetched, sha256 prefix `25f5e3b9c5308c57`);
  the installed openai 3.22.1 (`ChatCompletionChunk.usage`,
  `CompletionUsage`, `max_tokens` deprecation).
- Not run: Docker Compose and Grafana rendering. The dashboard's
  queries were parsed by promtool and answered by the native
  Prometheus; the panels themselves were not rendered.
- Figures 11.1 and 11.2: matplotlib, greyscale, 300 DPI, 4.55 in;
  Figure 11.2's data come from the labs (`figure_data.json`), and the
  tests assert the same values.

## Chapter 12: SLIs, SLOs and Error Budgets Across Four Layers

- Command: `make verify-ch12` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages)
- Date: 2026-10-13

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L12-01 | Burn rate and how long a budget lasts | `src/wrenholt/slo/errorbudget.py` | `tests/slo/test_error_budget.py` (every worked number) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L12-02 | The SLO file: header, availability, latency by request class | `src/wrenholt/slo/objectives.yaml` | `tests/slo/test_objectives.py` (Table 12.1; thresholds are the catalogue's and bucket boundaries) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L12-03 | An objective and a reason for none | `src/wrenholt/slo/objectives.yaml` | `tests/slo/test_objectives.py` | pass (SIMULATED cost threshold) | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L12-04 | The rules a reviewer would check | `src/wrenholt/slo/objectives.py` | `tests/slo/test_objectives.py` (five broken files refused) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L12-05 | The error-ratio expression | `src/wrenholt/slo/rules.py` | `tests/slo/test_rules.py`; `promtool test rules` (6 cases) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L12-06 | Two generated rules, wrapped | `deploy/compose/prometheus/rules/slo.rules.yaml` (the same rules on one line each) | `tests/slo/test_rules.py` (exact expressions); `promtool check rules`; native run | pass | not re-run: needs a running stack with data |
| L12-07 | Rule files and retention | `deploy/compose/prometheus/prometheus.yml` | `tests/slo/test_rules.py`; `promtool check config`; native run | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L12-08 | The SLI recorder | `src/wrenholt/slo/recorder.py` | `tests/unit/test_slo_api.py` (series at zero; one event per SLI); native run | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L12-09 | The guardrail in front of Linnet | `src/wrenholt/slo/recorder.py` | `tests/unit/test_slo_api.py` (refusals whole and streamed; 429 spends availability) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L12-10 | The error budget policy | `docs/error_budget_policy.md` | `tests/slo/test_error_budget.py` (the policy's thresholds) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L12-11 | FS-05 fault in the mock | `services/mock_llm/malformed.py` | `tests/slo/test_slo_labs.py` | pass (SIMULATED) | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L12-12 | FS-05 lab | `scripts/fs05_malformed_refund.py` | run command (2026-10-13); `tests/slo/test_slo_labs.py` asserts every number | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |
| L12-13 | Guardrail versions | `src/wrenholt/guardrail.py` | `tests/unit/test_slo_api.py` (rule ids on spans, never words) | pass (SIMULATED) | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L12-14 | FS-17 lab | `scripts/fs17_over_blocking.py` | run command (2026-10-13); `tests/slo/test_slo_labs.py` asserts every number | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience tests/drift
  tests/privacy` with `.native/bin` (otelcol-contrib, promtool) on
  `PATH` and `SEMCONV_GENAI_DIR` set: 267 passed. `pytest tests/lab`:
  8 passed. 275 tests: unit 181, slo 45, resilience 5, drift 22,
  lab 8, privacy 14. Thirty-nine are new.
- `ruff check`, `ruff format --check` and `mypy --strict`: clean.
  `uv lock --check`: 96 packages.
- Every source listing in Chapters 1 to 12 is in the repository (76
  checked; 29 captured outputs and queries skipped), except L10-03,
  superseded by L11-08 as approved. No Chapter 12 change supersedes
  a listing.
- Chapter 11's budget test now leaves out Chapter 12's two metrics,
  Chapter 10's combinations test includes them, and the queue test
  counts 199 points (11,940 in five minutes, within 12,000). The
  drift run records the API's SLI events and one guardrail refusal;
  the dashboard lint and the rename drill accept the recorded SLO
  names; a new drift test checks that every rule reads names a run
  produced. `drift.PROMQL_WORDS` gains `vector`.
- `promtool test rules tests/slo/slo_rules.test.yaml`: 6 cases pass,
  among them a malformed decision in a series born with it, which no
  rule sees, and the same decision in a series recorded at zero.
- Native run, 2026-10-13 12:58:52 UTC, 38 s: Collector 0.162.0 with
  the production profile and Prometheus 3.15.0 loading the generated
  rules (interval shortened to 5 s for the run), Linnet with
  guardrail version 2, orders and the mock as local processes; Tempo
  and Loki left out. 21 answers (HTTP 200) and 3 outcomes (204).
  Rules: 9 groups, 77 rules, health ok, no errors. Prometheus stored
  `wrenholt_slo_events_total` with `wrenholt_slo_sli` and
  `wrenholt_slo_good` (`true`, `false`), and
  `wrenholt_answer_time_to_first_chunk_seconds_bucket` with `le`
  0.5, 1, 2.5, 4, 6, 10 and +Inf: 28 series. The 5-minute refusal
  ratio read 0.2857 (6 of 21); no refund was decided, so no
  decision-validity ratio was recorded. All six panels of the SLO
  dashboard returned data.
- Sources read: SRE Workbook chapters 2 and 5 (quotes re-read) and
  the example error budget policy (fetched 2026-10-13); Prometheus
  v3.15.0 docs (configuration, command-line flags, feature flags,
  unit testing for rules).

## Chapter 13: Evaluation Signals and Drift in Production

- Command: `make verify-ch13` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages)
- Date: 2026-10-13

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L13-01 | Evaluation sampling by trace ID | `src/wrenholt/evaluation/sampling.py` | `tests/unit/test_evaluation.py` (the rule; a rate of 0.1 within 0.01 over 10,000 IDs) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L13-02 | A verdict and the evaluator interface | `src/wrenholt/evaluation/evaluators.py` | `tests/unit/test_evaluation.py` (known answers); `mypy --strict` | pass (SIMULATED evaluators) | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L13-03 | The adapter for outside evaluators | `src/wrenholt/evaluation/evaluators.py` | `tests/unit/test_evaluation.py` (label and score mapped; unmapped label refused) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L13-04 | The result emitter | `src/wrenholt/evaluation/emitter.py` | `tests/unit/test_evaluation.py` (linked, no content, series at zero, slices); `tests/drift/test_events_drift.py`; native run | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L13-05 | Evaluating online | `src/wrenholt/evaluation/online.py` | `tests/unit/test_evaluation.py` (sampled, not sampled, no span, streamed, failing evaluator); native run | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L13-06 | The share check | `src/wrenholt/evaluation/drift.py` | `tests/unit/test_evaluation.py` (waits for 30; stable series; new baseline); `tests/slo/test_eval_labs.py` (z 22.5 and 21.7) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L13-07 | Groundedness's objective | `src/wrenholt/slo/objectives.yaml` | `tests/slo/test_objectives.py`; `tests/slo/test_rules.py` (10 groups, 86 rules); native run | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L13-08 | The metrics queue, superseding L11-08 | `deploy/compose/otelcol/config.production.yaml` | `tests/unit/test_pipeline_config.py` (213 points; 12,780 within 13,000); native run | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L13-09 | FS-10 lab | `scripts/fs10_prompt_regression.py` | run command (2026-10-13); `tests/slo/test_eval_labs.py` asserts every number | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |
| L13-10 | FS-09 lab, index swap | `scripts/fs09_index_swap.py` | run command (2026-10-13); `tests/slo/test_eval_labs.py` asserts every number | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |
| L13-11 | FS-16 lab | `scripts/fs16_intent_drift.py` | run command (2026-10-13); `tests/slo/test_eval_labs.py` asserts every number | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience tests/drift
  tests/privacy` with `.native/bin` (otelcol-contrib, promtool) on
  `PATH` and `SEMCONV_GENAI_DIR` set: 284 passed. `pytest tests/lab`:
  8 passed. 292 tests: unit 191, slo 51, resilience 5, drift 23,
  lab 8, privacy 14. Seventeen are new.
- `ruff check`, `ruff format --check` and `mypy --strict` (201
  files): clean. `uv lock --check`: 96 packages.
- Every source listing in Chapters 1 to 13 is in the repository (84
  checked; 32 captured outputs and queries skipped), except L10-03,
  superseded by L11-08 as approved, and L11-08, superseded by L13-08
  (proposed with this chapter).
- Chapter 12's tests now expect groundedness's objective (0.99,
  counted from evaluation results) and 10 groups of 86 rules; the
  budget test counts 14 combinations for the evaluation counter,
  1,997 series and 213 points; the queue test counts 12,780 points
  in five minutes against 13,000. The drift run emits one answer's
  evaluation results, and a new drift test checks the event name and
  that every attribute on the events is registered.
- The three labs printed exactly Listings L13-09, L13-10 and L13-11.
- Native run, 2026-10-13 17:43:19 UTC, 48.5 s: Collector 0.162.0 with
  the production profile, Prometheus 3.15.0 loading the generated
  rules and Loki 3.7.8, Linnet with an evaluation rate of 1.0, orders
  and the mock as local processes; Tempo left out. 8 answers, 3 of
  them streamed (HTTP 200). Rules: 10 groups, 86 rules, health ok.
  Prometheus stored `wrenholt_evaluation_results_total` with 10
  label sets: intent (order 1, other 1, policy 2, refund 4), refusal
  by prompt version 1 (answer 8, refusal 0), groundedness (grounded
  2, ungrounded 0) and policy accuracy by index build (correct 2,
  incorrect 0). The 5-minute groundedness error ratio read 0. Loki
  held 20 evaluation events, found by
  `{service_name="linnet-api"} | scope_name="wrenholt.evaluation"`,
  each with its attributes, trace ID and span ID as structured
  metadata and an empty line; a query by event name found nothing,
  and a probe through the same configuration confirmed that Loki does
  not keep the event name. All four panels of the evaluation
  dashboard returned data.
- Sources read: the GenAI events document at
  semantic-conventions-genai `bcc7f9c` (pinned checkout); the
  installed opentelemetry-api 1.45.0 (`Logger.emit` signature; no
  events module); Zheng et al., NeurIPS 2023 (poster page).

## Chapter 14: Alerting on Burn Rates and Symptoms

- Command: `make verify-ch14` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages)
- Date: 2026-10-13

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L14-01 | The three tiers | `src/wrenholt/slo/alerts.py` | `tests/slo/test_alerts.py` (windows, burn rates, a short window a twelfth of the long one) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L14-02 | Which tiers an SLO gets | `src/wrenholt/slo/alerts.py` | `tests/slo/test_alerts.py` (Table 14.2; 18 alerts) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L14-03 | The alert expression | `src/wrenholt/slo/alerts.py` | `tests/slo/test_alerts.py` (exact lines; thresholds; recorded series only); promtool | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L14-04 | Detection time and budget spent | `src/wrenholt/slo/alerts.py` | `tests/slo/test_alerts.py` (Table 14.1; Section 14.3.3) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L14-05 | A generated Grafana rule | `deploy/compose/grafana/provisioning/alerting/slo-alerts.yaml` | `tests/slo/test_alerts.py` (committed equals generated; structure). Grafana not run | pass (format per v13.2.3 docs) | static: format per v13.2.3 docs; Grafana ran with it in CI run 39411828181, rules not seen firing |
| L14-06 | Contact point and notification policy | `deploy/compose/grafana/provisioning/alerting/slo-alerts.yaml` | `tests/slo/test_alerts.py` (webhook setting; routes). Grafana not run | pass (format per v13.2.3 docs) | static: format per v13.2.3 docs; Grafana ran with it in CI run 39411828181, rules not seen firing |
| L14-07 | FS-03's promtool test | `tests/slo/slo_alerts.test.yaml` | promtool 3.15.0 `test rules` (4 cases), run by `tests/slo/test_alerts.py` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L14-08 | The availability runbook | `docs/runbooks.md` | `tests/slo/test_alerts.py` (every alert's link has a section) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L14-09 | The lab's alert question | `src/wrenholt/labs/paging_lab.py` | `tests/slo/test_paging_lab.py` | pass (SIMULATED) | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L14-10 | Paging lab | `scripts/fs02_fs03_paging.py` | run command (2026-10-13); `tests/slo/test_paging_lab.py` asserts every number | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience tests/drift
  tests/privacy` with `.native/bin` (otelcol-contrib, promtool) on
  `PATH` and `SEMCONV_GENAI_DIR` set: 298 passed. `pytest tests/lab`:
  8 passed. 306 tests: unit 191, slo 65, resilience 5, drift 23,
  lab 8, privacy 14. Fourteen are new.
- `ruff check`, `ruff format --check` and `mypy --strict` (207
  files): clean. `uv lock --check`: 96 packages.
- Every source listing in Chapters 1 to 14 is in the repository (93
  checked; 33 captured outputs and queries skipped), except L10-03
  and L11-08, superseded as approved. No Chapter 14 change
  supersedes a listing.
- `promtool test rules tests/slo/slo_alerts.test.yaml` (promtool
  3.15.0, from `tests/slo`): 4 cases pass through the generated
  recording rules. FS-03: fast page at 6h1m, slow page at 6h3m, fast
  page firing at 6h33m and reset at 6h34m (the last failures were
  sampled at 6h30m). FS-02: 6h9m and 6h22m. A five-minute brownout:
  no page, the 5-minute ratio alone over 0.144. One failure at ten
  answers an hour: both page tiers' windows over their thresholds,
  no page. With only the recording groups in `group_eval_order`, two
  runs of the same test disagreed; every group is listed now, and
  repeated runs agree.
- The generated files regenerate byte for byte; `promtool check
  rules` accepts both rule files (96 recording rules, 18 alerting
  rules).
- Chapter 12's rule test counts 96 rules in 10 groups (valid events
  over 6 hours added for the slow page's minimum).
- The paging lab printed exactly Listing L14-10.
- Grafana was not run: its 13.2.3 release is downloaded from
  dl.grafana.com, which this environment's proxy refuses (HTTP 403).
  The provisioning file follows the v13.2.3 documentation and the
  shape the Phase 1.5 alert smoke used; the CI stack job provisions
  it after the push. No native run for Chapter 14.
- Sources read: SRE Workbook chapter 5 (re-read 2026-10-13); Grafana
  v13.2.3 alert file provisioning (fetched at the tag); Prometheus
  v3.15.0 docs (querying basics, unit testing for rules).

## Chapter 15: Diagnosing Production AI Failures

- Command: `make verify-ch15` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages)
- Date: 2026-10-19

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L15-01 | Nearest-rank percentiles and the spread | `src/wrenholt/diagnosis.py` | `tests/unit/test_diagnosis.py` (18 answers; mean 1.70, p50 0.40, p95 3.00; 9 over 2.5 s) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L15-02 | The provider check (L1) | `src/wrenholt/diagnosis.py` | `tests/unit/test_diagnosis.py` (median +2.60 s; own time +0.00 s; gone once the brownout is removed) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L15-03 | The retrieval check (L3) | `src/wrenholt/diagnosis.py` | `tests/unit/test_diagnosis.py` (12 of 12 empty; embedders) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L15-04 | The vault's gate | `src/wrenholt/labs/diagnosis_lab.py` | `tests/unit/test_diagnosis.py` (no reason, wrong role, granted; log without content) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L15-05 | Bundle replay against the mock | `src/wrenholt/labs/diagnosis_lab.py` | `tests/unit/test_diagnosis.py` (0 passages, then 2; changed prompt refused) | pass (SIMULATED) | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L15-06 | `wrenholt diagnose` on the recorded hour | `scripts/wrenholt_cli.py` | run command (2026-10-19); `tests/unit/test_diagnosis.py` | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |
| L15-07 | `wrenholt replay` of one trace | `scripts/wrenholt_cli.py` | run command (2026-10-19); `tests/unit/test_diagnosis.py` | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience tests/drift
  tests/privacy`: 305 passed. `pytest tests/lab`: 8 passed. 313
  tests: unit 198, slo 65, resilience 5, drift 23, lab 8, privacy 14.
  Seven are new. The CLI was then renamed `scripts/wrenholt_cli.py`,
  because `scripts/wrenholt.py` shadowed the package for mypy; ruff,
  mypy and the diagnosis tests were rerun after the rename.
- `ruff check`, `ruff format --check` and `mypy --strict` (211
  files): clean. `uv lock --check`: 96 packages.
- Every source listing in Chapters 1 to 15 is in the repository (98
  checked; 35 captured outputs skipped), except L10-03 and L11-08,
  superseded as approved.
- The fixture `tests/fixtures/diagnosis/fs08_behind_fs02.json` was
  recorded on 2026-10-19 from an in-process Linnet with the mock
  provider; `captured.json` holds the synthetic questions. The CLI
  printed exactly Listings L15-06 and L15-07.
- No native run. The TraceQL query follows the Tempo v3.1.0 docs
  (fetched at the tag) and the LogQL query Chapter 13's Loki run;
  neither was executed against Tempo or Loki here.
- Sources read: SRE book chapter 22 (2026-10-19); TraceQL docs at
  Tempo v3.1.0.

## Chapter 16: Timeouts, Retries, Rate Limits and Circuit Breakers

- Command: `make verify-ch16` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages)
- Date: 2026-10-19

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L16-01 | One deadline per answer | `src/wrenholt/gateway/deadlines.py` | `tests/unit/test_guarded.py` (spent deadline refused; attempt cut at the deadline) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L16-02 | The process-wide retry budget | `src/wrenholt/gateway/retry.py` | `tests/resilience/test_controls.py` (Hypothesis: grants exactly its rolling minute) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L16-03 | Retry decisions under the deadline and the budget | `src/wrenholt/gateway/retry.py` | `tests/resilience/test_controls.py` (backoff bounds; never past the deadline); `tests/unit/test_guarded.py` (6 s retry-after: Chapter 4 stops, 9 s left retries, 5 s left stops) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L16-04 | The breaker's states | `src/wrenholt/gateway/breaker.py` | `tests/resilience/test_controls.py` (opens on the fifth, one probe, closes; only the provider's failures; Hypothesis) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L16-05 | The guarded attempt | `src/wrenholt/gateway/guarded.py` | `tests/unit/test_guarded.py` (breaker, bulkhead and deadline refusals send nothing; FS-18 not retried) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L16-06 | The refund under the deadline and the budget | `src/wrenholt/tools/guarded.py` | `tests/unit/test_guarded.py` (cut at the deadline; retry refused with the budget spent) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L16-07 | The protective controls under load | `scripts/protect_lab.py` | run command (2026-10-19); `tests/unit/test_guarded.py` (every figure) | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience tests/drift
  tests/privacy`: 319 passed. `pytest tests/lab`: 8 passed. 327
  tests: unit 206, slo 65, resilience 11, drift 23, lab 8, privacy 14.
  Fourteen are new; the drift fixture now makes a guarded call whose
  breaker opens, so the five new attribute names are emitted names.
- `ruff check`, `ruff format --check` and `mypy --strict` (220
  files): clean. `uv lock --check`: 96 packages.
- Every source listing in Chapters 1 to 16 is in the repository (104
  checked; 36 captured outputs skipped), except L10-03 and L11-08,
  superseded as approved. The availability runbook's Chapter 16 note
  follows the block Listing L14-08 shows, which is unchanged.
- No native run: the lab uses a fake clock, and the TraceQL query in
  Section 16.4 was not executed against Tempo.
- Sources read: SRE book chapter 22, the retry quotes (2026-10-19);
  Amazon Builders' Library, timeouts, retries and backoff with
  jitter (2026-10-19). The Azure circuit breaker pattern is
  paraphrased, not quoted.

## Chapter 17: Fallbacks, Degraded Modes and Load Shedding

- Command: `make verify-ch17` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages)
- Date: 2026-10-19

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L17-01 | The chain's walk, with exercise | `src/wrenholt/gateway/fallback.py` | `tests/unit/test_fallback.py` (A rate-limited: B answers, then A; exercise; retired fallback; spent deadline) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L17-02 | Price ratio, affordability, when to move | `src/wrenholt/gateway/fallback.py` | `tests/unit/test_fallback.py` (B affordable, `mock-a-large` refused at start-up) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L17-03 | The ladder without a model | `src/wrenholt/orchestrator/degraded.py` | `tests/unit/test_fallback.py` (brief, citation, stale, no passage, refund) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L17-04 | Admission and the degraded path in the API | `src/wrenholt/api/app.py` | `tests/unit/test_fallback.py` (no room: brief and 503; A and B down: brief); Hypothesis property of `Admission` | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L17-05 | The `degraded` tail-sampling policy | `deploy/compose/otelcol/config.production.yaml` | `tests/unit/test_pipeline_config.py`; `otelcol-contrib validate` with dummy endpoints and key | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L17-06 | Fallbacks, costs and shedding | `scripts/fallback_lab.py` | run command (2026-10-19); `tests/unit/test_fallback.py` (every figure) | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience tests/drift
  tests/privacy`: 327 passed. `pytest tests/lab`: 8 passed. 335
  tests: unit 214, slo 65, resilience 11, drift 23, lab 8, privacy 14.
  Eight are new; the drift fixture now makes a call that falls back
  to provider B, so the four new attribute names are emitted names.
- `ruff check`, `ruff format --check` and `mypy --strict` (226
  files): clean. `uv lock --check`: 96 packages.
- Every source listing in Chapters 1 to 17 is in the repository (109
  checked; 37 captured outputs skipped), except L10-03 and L11-08,
  superseded as approved. The `degraded` policy follows the baseline,
  after the block Listing L10-01 shows; the runbook note follows the
  block Listing L14-08 shows.
- The mock provider can now serve provider B's models in process
  (`running_provider(provider="b")`); `MOCK_LLM_PROVIDER` still sets
  the process default, and Listing L01-02's code is unchanged.
- No native run: the lab uses a fake clock, and the TraceQL queries
  in Section 17.4 were not executed against Tempo.
- Sources read: SRE book chapter 22, the load shedding, queue and
  unused code path quotes (2026-10-19).

## Chapter 18: Failure Injection, Load and Chaos Experiments

- Command: `make verify-ch18` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages)
- Date: 2026-10-20

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L18-01 | Gradual and impulse arrivals | `src/wrenholt/load.py` | `tests/unit/test_experiments.py` (7,200 on the ramp; 4,500 on the impulse; the same every time) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L18-02 | `drive`, without waiting | `src/wrenholt/load.py` | `tests/unit/test_experiments.py` (every call starts before the first ends; an exception is a result) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L18-03 | Experiments as data | `src/wrenholt/experiments.py` | `tests/unit/test_experiments.py` (FS-01 to FS-18; 14.4 and 0.99 read from the book's files) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L18-04 | Judging and running | `src/wrenholt/experiments.py` | `tests/unit/test_experiments.py` (held, BROKEN, no evidence; detected, MISSED; FS-09, FS-11, FS-18 run and recorded) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L18-05 | The breaking-point model | `src/wrenholt/labs/breaking_lab.py` | `tests/unit/test_experiments.py` (windows and recovery) | pass (SIMULATED) | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L18-06 | The eighteen experiments | `scripts/experiments.py` | run command (2026-10-20), recorded in `experiments/latest.json` | pass (SIMULATED) | pass: output re-run 20 Oct 2026, same verdicts; header shows today's version (appH) |
| L18-07 | The breaking point, and past it | `scripts/breaking_lab.py` | run command (2026-10-20); `tests/unit/test_experiments.py` | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience tests/drift
  tests/privacy`: 336 passed. `pytest tests/lab`: 8 passed. 344
  tests: unit 223, slo 65, resilience 11, drift 23, lab 8, privacy 14.
  Nine are new.
- `ruff check`, `ruff format --check` and `mypy --strict` (232
  files): clean. `uv lock --check`: 96 packages.
- Every source listing in Chapters 1 to 18 is in the repository (114
  checked; 39 captured outputs skipped), except L10-03 and L11-08,
  superseded as approved.
- The experiment run: 18 run, 0 hypotheses failed, about two minutes;
  FS-15 runs the Collector binary from `.native/bin`, as in Chapter
  10. No other native run, and no Compose stack.
- Sources read: SRE book chapter 22, the load testing, breaking point,
  degraded mode and noncritical backend quotes (2026-10-20).

## Chapter 19: Incident Response and Postmortems for AI Systems

- Command: `make verify-ch19` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages)
- Date: 2026-10-20

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L19-01 | AI severities | `src/wrenholt/incidents.py` | `tests/unit/test_incidents.py` (severity follows the SLO and only rises) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L19-02 | Grafana's notifications into one record | `src/wrenholt/incidents.py` | `tests/unit/test_incidents.py` (open, repeat, join, mitigate, reopen; restart) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L19-03 | The incident service | `src/wrenholt/api/incidents.py` | `tests/unit/test_incidents.py` (POST /alerts, GET /incidents, the draft, 404) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L19-04 | The service in compose | `deploy/compose/docker-compose.yml` | `tests/unit/test_incidents.py` (parsed; Grafana's default webhook); not started | pass (parsed only) | pass: stack ran in CI run 39411828181 |
| L19-05 | The postmortem's completeness check | `src/wrenholt/incidents.py` | `tests/unit/test_incidents.py` (nine gaps; end-user data blocks the close) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L19-06 | The game day, FS-03 and FS-07 | `scripts/game_day.py` | run command (2026-10-20); `tests/unit/test_incidents.py` | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience tests/drift
  tests/privacy`: 343 passed. `pytest tests/lab`: 8 passed. 351
  tests: unit 230, slo 65, resilience 11, drift 23, lab 8, privacy 14.
  Seven are new.
- `ruff check`, `ruff format --check` and `mypy --strict` (237
  files): clean. `uv lock --check`: 96 packages.
- Every source listing in Chapters 1 to 19 is in the repository (119
  checked; 40 captured outputs skipped), except L10-03 and L11-08,
  superseded as approved.
- No Docker run: the compose file is parsed, not started. The game
  day's trace comes from a real gateway call to two addresses that
  refuse connections; its FS-07 finding comes from Chapter 9's lab.
- Sources read: SRE book chapter 15; the abstracts of Yan et al.
  (arXiv 2504.08865) and Chu et al. (arXiv 2501.12469); Grafana's
  webhook notifier docs at v13.2.3; Tempo's API docs at v3.1.0
  (2026-10-20).

## Chapter 20: Reliability in CI/CD and the Reliability Programme

- Command: `make verify-ch20` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages)
- Date: 2026-10-20

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| L20-01 | Change types and their CI gates | `src/wrenholt/gates.py` | `tests/unit/test_gates.py` (classification by path; `ci` runs only the gates needed) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L20-02 | The evaluation gate | `src/wrenholt/gates.py` | `tests/unit/test_gates.py` (FS-10 blocked, version 1 passes; cases weighted by the mix) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L20-03 | Canary signals, the split by version, the decision | `src/wrenholt/gates.py` | `tests/unit/test_gates.py` (wait, promote, roll back; one-sided; inside the budget; FS-11) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L20-04 | The budget gate | `src/wrenholt/gates.py` | `tests/unit/test_gates.py` (held; fix ships; outside cause; nothing exhausted) | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| L20-05 | The gates workflow | `.github/workflows/gates.yml` | `tests/unit/test_gates.py` (parsed); not run in GitHub Actions | pass (parsed only) | pass: gates run 39418580071 on pull request #1 (log not read); local mirror: contract, drift (3 skipped) and evaluation passed |
| L20-06 | The gates lab, FS-10 and FS-11 | `scripts/gates.py lab` | run command (2026-10-20); `tests/unit/test_gates.py` | pass (SIMULATED) | pass: output re-run 20 Oct 2026, identical |
| L20-07 | The self-assessment | `scripts/gates.py assess` | run command (2026-10-20); `tests/unit/test_gates.py` | pass | pass: output re-run 20 Oct 2026, identical |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience tests/drift
  tests/privacy`: 354 passed. `pytest tests/lab`: 8 passed. 362
  tests: unit 241, slo 65, resilience 11, drift 23, lab 8, privacy 14.
  Eleven are new.
- `ruff check`, `ruff format --check` and `mypy --strict` (242
  files): clean. `uv lock --check`: 96 packages.
- Every source listing in Chapters 1 to 20 is in the repository (124
  checked; 42 captured outputs skipped), except L10-03 and L11-08,
  superseded as approved.
- No Docker run, and no GitHub Actions run: the workflow is parsed,
  and `ci` runs with a stand-in for its subprocesses. The canary's
  spans come from real gateway calls to two in-process mock
  providers; the endpoint move and the newer model are simulated.
- Sources read: *The Site Reliability Workbook*, chapter 16,
  Canarying Releases, fetched twice with the quotes re-checked
  (2026-10-20).

## Appendix A: Telemetry Contract Reference

- Command: `make verify-appA` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages)
- Date: 2026-10-20

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| LA-01 | Tempo's 14-day retention | `deploy/compose/tempo/tempo.yaml` | `tests/drift/test_reference_drift.py` (retention); native Tempo 3.1.0 started, `/status/config` shows `block_retention: 336h0m0s` twice, ready | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| LA-02 | Loki's 14-day retention | `deploy/compose/loki/loki.yaml` | `tests/drift/test_reference_drift.py` (retention); native Loki 3.7.8 `-verify-config` passed (`retention_enabled: true`, `retention_period: 2w`), started ready | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| LA-03 | The reference check | `scripts/contract_reference.py --check` | run command (2026-10-20); `tests/drift/test_reference_drift.py` | pass | pass: output re-run 20 Oct 2026, identical |
| Tables | Every table of the appendix | `docs/telemetry_contract.md` | generated by `src/wrenholt/telemetry/reference.py`; `tests/drift/test_reference_drift.py` (current; spans; events; counts) | pass | pass: tests re-run 20 Oct 2026 |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience tests/drift
  tests/privacy`: 360 passed. `pytest tests/lab`: 8 passed. 368
  tests: unit 241, slo 65, resilience 11, drift 29, lab 8, privacy 14.
  Six are new.
- `ruff check`, `ruff format --check` and `mypy --strict` (245
  files): clean. `uv lock --check`: 96 packages.
- Every source listing in Chapters 1 to 20 and Appendix A is in the
  repository (126 checked; 43 captured outputs skipped), except
  L10-03 and L11-08, superseded as approved.
- Retention corrected with the author's approval: the privacy
  contract said metrics 30 days while Prometheus keeps 35, and
  neither Tempo nor Loki set a retention. Neither ran long enough
  to delete anything; no Docker run.

## Appendices B to H

- Command: `make verify-appendices` (or the commands under that target)
- Interpreter: CPython 3.14.4 via uv 0.11.7, Linux sandbox
- Dependencies: `uv.lock` unchanged (96 packages)
- Date: 2026-10-20

| Listing | What it shows | File | Checked by | Phase 2 | Phase 3 |
|---|---|---|---|---|---|
| LC-01 | The development pipeline | `deploy/compose/otelcol/config.yaml` | earlier chapters' tests; listing check | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| LC-02 | The production-like pipeline | `deploy/compose/otelcol/config.production.yaml` | earlier chapters' tests; listing check | pass | pass: listing verbatim in repo; tests re-run 20 Oct 2026 |
| LC-03 | The load-balancing tier | `deploy/compose/otelcol/loadbalancing.yaml` | validated in Chapter 10, not run; listing check | pass (validated only) | pass: native load-balancing exercise, 20 Oct 2026 |
| LH-01 | Jaeger v2 in place of Tempo | `deploy/compose/docker-compose.jaeger.yml` | `tests/unit/test_appendices.py` (parsed); not run | pass (parsed only) | failed: alternatives run 39418580084 validated the override and started the stack, but the probes used routes Jaeger 2.21.0 removed (HTTP 404); probes corrected and passed natively; GitHub rerun pending |
| Tables | Every generated table of Appendices B to H | `src/wrenholt/appendices.py` | `tests/unit/test_appendices.py` | pass | pass: tests re-run 20 Oct 2026 |
| Queries | 45 PromQL, 7 TraceQL, 3 LogQL, as printed | Appendix D | sent to native Prometheus 3.15.0, Tempo 3.1.0 and Loki 3.7.8 on empty stores: all accepted (parse only, no data) | pass | pass: parse only, native backends, 20 Oct 2026 |

Same run, other checks:

- `pytest tests/unit tests/slo tests/resilience tests/drift
  tests/privacy`: 365 passed. `pytest tests/lab`: 8 passed. 373
  tests: unit 246, slo 65, resilience 11, drift 29, lab 8, privacy 14.
  Five are new.
- `ruff check`, `ruff format --check` and `mypy --strict` (247
  files): clean. `uv lock --check`: 96 packages.
- Every source listing in Chapters 1 to 20 and Appendices A to H is
  in the repository (130 checked; 43 captured outputs skipped),
  except L10-03 and L11-08, superseded as approved.
- Not run: Docker, the Jaeger override, the otel-lgtm quick start.

## Phase 3: Technical Validation (open)

Results are Passed (executed), Failed (executed, failure recorded),
Static (configuration or parse only), Not run, or Blocked. Provider
results come from the mock and stay SIMULATED.

### GitHub Actions: compose-smoke run 39392390376

Branch `phase2-sync`, commit 3c83f57, 20 Oct 2026; read from the
run's job logs as shared by the author.

| Item | Result | Evidence |
|---|---|---|
| Check 1: start stack | Passed | 39 s; every container running and healthy, Tempo and Loki with 14-day retention among them |
| Checks 1-7: smoke test | Passed | 19 s |
| Checks 10-14 and 18 | Passed | four services healthy; Linnet answered; provider B served only its model; refund 201 then 200, one refund ID; 2 Linnet traces in Tempo; 4 dashboards provisioned |
| Check 15 | Failed | `HTTP 200, 0 series`: the check asked for `job="linnet-api"`, but since Chapter 6's `service.namespace` Prometheus names the job `wrenholt/linnet-api` |
| Checks 16 and 17 | Not run | skipped after check 15 failed |
| Check 8: shut down cleanly | Passed | 1 m 1 s |
| Check 9: alert smoke | Not run | skipped; it needs the stack smoke job |
| Config lint: rules | Passed | 6 s |
| Config lint: Collector validates its own config | Failed | `processors::redaction: hmac_key must not be empty when hash_function is "hmac-sha256"`: the step passed no `REDACTION_HMAC_KEY` |
| Config lint: promtool, drift suite | Not run | skipped after the failure |
| Release gates | Not run | no pull request yet |

### Corrections approved by the author (20 Oct 2026)

- `.github/workflows/compose-smoke.yml`: the validate step passes
  the development-only key compose already uses; production sets
  its own `REDACTION_HMAC_KEY`, and redaction itself is unchanged.
- `scripts/smoke_wrenholt.py`: check 15 asks for
  `job="wrenholt/linnet-api"` and still requires at least one series.
- `.github/workflows/gates.yml`: fetches the native Collector before
  the gates, so the contract gate's Collector tests run instead of
  skipping. Listing L20-05, in the book's files and in the Chapter
  20 document, matches the workflow byte for byte.
- `.github/workflows/alternatives.yml` and
  `scripts/smoke_alternatives.py`: Appendix H's Jaeger alternative
  and quick start. GitHub runs `workflow_dispatch` only for
  workflows on the default branch, so until the file is there it
  also runs on pull requests that change it, the override or the
  smoke script.

### Local checks after the corrections (20 Oct 2026)

- Collector 0.162.0 `validate` with the CI step's environment:
  failed without the key, with the message CI reported; passed with
  it. Static validation only.
- Native stand-in for the stack, no Docker: the same Prometheus,
  Tempo, Loki and Collector binaries and configuration files on
  local ports, with mock providers A and B, orders and Linnet under
  uvicorn. Checks 10-15 passed (check 15: 1 series under
  `wrenholt/linnet-api`). Check 16: Collector stopped, 20 of 20
  answered, slowest 60 ms. Check 17: Collector restarted, accepted
  spans 200 -> 250. Check 18 not run natively: no Grafana binary.
- `pytest tests/unit tests/slo tests/resilience tests/drift
  tests/privacy`: 367 passed. `pytest tests/lab`: 8 passed. 375
  tests: unit 248, slo 65, resilience 11, drift 29, lab 8, privacy 14.
  Two are new: the alternatives workflow, and its probes against
  canned Jaeger and Grafana replies.
- `ruff check`, `ruff format --check` and `mypy --strict` (248
  files): clean. `uv lock --check`: 96 packages. Listings: 130
  checked, 43 captured outputs skipped, 0 missing, L10-03 and
  L11-08 superseded as approved. `scripts/contract_reference.py
  --check`: reference is current.

### GitHub Actions: compose-smoke run 39411828181

Branch `phase2-sync`, commit e602e8c, 20 Oct 2026: success in 5 m 43
s. Config lint 29 s, Stack smoke (checks 1-8, 10-17) 2 m 55 s, Alert
smoke (check 9) 2 m 43 s, read from the public run page; the step
logs need a sign-in and were not read. A job succeeds only when every
step it ran succeeded, and none of these steps continues on error, so
every check passed: the Collector validate, promtool and the drift
suite against the pinned GenAI checkout, checks 1-8 and 10-17 on
Docker (16 and 17 for the first time), and check 9.

### Collector load-balancing tier: native exercise (20 Oct 2026)

Passed, natively, not on Docker. `loadbalancing.yaml` and two
samplers running `config.production.yaml`, on otelcol-contrib
0.162.0. Harness changes only: listen addresses (the tier on
127.0.0.1, the samplers on 127.0.0.2 and 127.0.0.3, their health
checks and own metrics too); `/etc/hosts` gave `otel-sampler` both
sampler addresses; each sampler's trace exporter reached a local
OTLP sink through `TEMPO_OTLP_HTTP`. The committed files are
unchanged, and `/etc/hosts` was restored.

- 40 traces of 3 spans, every span in its own request, every span
  with ERROR status so the errors policy keeps every trace.
- The tier resolved two backends. One sampler received 21 traces (63
  spans), the other 19 (57); no trace was split; every trace arrived
  complete at one sampler and was kept.
- A first attempt's sink could not read gzip bodies (a harness
  defect, fixed); the Collectors' own counters already showed whole
  traces then: 72 and 48 spans, 24 and 16 traces sampled.

### Version pins

There are 40 pins marked `recheck = true`; the count of 41 reported
earlier included the `[meta]` line that names the flag. Every pin is
a published release, none yanked, checked against the PyPI JSON API
and the projects' release tags on 20 Oct 2026. No pin was changed:
newer releases are listed for a decision, not adopted.

| Pin | Pinned | Release found | Newest seen (20 Oct 2026) |
|---|---|---|---|
| `opentelemetry-api` | 1.45.0 | PyPI, uploaded 2026-09-25 | 1.45.1 |
| `opentelemetry-sdk` | 1.45.0 | PyPI, uploaded 2026-09-25 | 1.45.1 |
| `opentelemetry-exporter-otlp-proto-http` | 1.45.0 | PyPI, uploaded 2026-09-25 | 1.45.1 |
| `opentelemetry-semantic-conventions` | 0.66b0 | PyPI, uploaded 2026-09-25 | 0.66b1 |
| `opentelemetry-instrumentation-fastapi` | 0.66b0 | PyPI, uploaded 2026-09-25 | 0.66b1 |
| `opentelemetry-instrumentation-httpx` | 0.66b0 | PyPI, uploaded 2026-09-25 | 0.66b1 |
| `opentelemetry-instrumentation-logging` | 0.66b0 | PyPI, uploaded 2026-09-25 | 0.66b1 |
| `openai` | 3.22.1 | PyPI, uploaded 2026-09-30 | 3.35.1 |
| `anthropic` | 1.9.0 | PyPI, uploaded 2026-09-28 | 1.15.0 |
| `httpx2` | 2.13.1 | PyPI, uploaded 2026-09-23 | 2.15.1 |
| `fastapi` | 0.142.1 | PyPI, uploaded 2026-09-29 | 0.151.0 |
| `uvicorn` | 0.54.0 | PyPI, uploaded 2026-09-25 | same |
| `pydantic` | 2.13.5 | PyPI, uploaded 2026-08-28 | 2.14.1 |
| `pydantic-settings` | 2.15.0 | PyPI, uploaded 2026-08-07 | 2.16.0 |
| `pyyaml` | 6.0.3 | PyPI, uploaded 2025-09-25 | same |
| `pytest` | 9.1.1 | PyPI, uploaded 2026-06-19 | same |
| `pytest-asyncio` | 1.4.0 | PyPI, uploaded 2026-05-26 | same |
| `hypothesis` | 6.168.3 | PyPI, uploaded 2026-09-28 | 6.170.5 |
| `mypy` | 2.3.1 | PyPI, uploaded 2026-08-15 | 2.4.0 |
| `ruff` | 0.16.9 | PyPI, uploaded 2026-09-24 | 0.17.1 |
| `types-pyyaml` | 6.0.12.20260906 | PyPI, uploaded 2026-09-06 | same |
| `opentelemetry-instrumentation-openai-v2` | 2.4b0 | PyPI, uploaded 2026-05-01 | same |
| `opentelemetry-util-genai` | 0.4b0 | PyPI, uploaded 2026-05-01 | 1.2b0 |
| `httpx` | 0.28.1 | PyPI, uploaded 2024-12-06 | same |
| `locust` | 2.46.6 | PyPI, uploaded 2026-09-17 | 2.46.7 |
| `uv` | 0.11.7 | PyPI, uploaded 2026-04-15 | 0.13.3 |
| `presidio-analyzer` | 2.2.364 | PyPI, uploaded 2026-07-22 | same |
| `python` | v3.14.7 | tag in `python/cpython` | v3.15.0 |
| `otelcol` | v0.162.0 | tag in `open-telemetry/opentelemetry-collector-releases` | v0.163.1 |
| `prometheus` | v3.15.0 | tag in `prometheus/prometheus` | same |
| `tempo` | v3.1.0 | tag in `grafana/tempo` | same |
| `loki` | v3.7.8 | tag in `grafana/loki` | same |
| `grafana` | v13.2.3 | tag in `grafana/grafana` | v13.2.4 |
| `jaeger` | v2.21.0 | tag in `jaegertracing/jaeger` | v2.22.0 |
| `otel-lgtm` | v0.34.0 | tag in `grafana/docker-otel-lgtm` | v0.37.0 |
| `compose` | v5.5.1 | tag in `docker/compose` | v5.6.0 |
| `semconv` | v1.44.0 | tag in `open-telemetry/semantic-conventions` | same |
| otelcol-contrib binary | 0.162.0 | release archives, SHA-256 checked by `scripts/fetch_collector.sh` | 0.163.1 |
| `python:3.14.7-slim` | 3.14.7 | pulled by run 39411828181 | 3.14.8 |
| GenAI conventions | bcc7f9c | commit in `semantic-conventions-genai`, which has no release tags | HEAD 547934a (18 Oct 2026), 23 commits later |

Run 39411828181 pulled the Prometheus, Tempo, Loki, Grafana,
Collector and Python images, so those tags exist. The Jaeger and
otel-lgtm images are pulled first by the alternatives workflow.

The GenAI conventions are still unreleased. Since the pin, HEAD has
renamed two metrics Wrenholt emits,
`gen_ai.client.operation.time_to_first_chunk` and
`gen_ai.client.operation.time_per_output_chunk`, to
`gen_ai.client.inference.time_to_first_chunk` and
`gen_ai.client.inference.time_per_output_chunk`; added
`gen_ai.client.inference.duration` and three `gen_ai.main_agent.*`
attributes; and renamed the span model `gen_ai.inference.client` to
`gen_ai.client.inference`. Nothing breaks at the pinned commit;
moving the pin follows Appendix B and needs a decision.

### Captured outputs (43 listings)

Every listing that shows a command's output was re-run on 20 Oct 2026
from the repository root and compared with the listing:

- 25 identical.
- 7 identical apart from timings (L01-05, L03-05, L04-06, L07-06,
  L08-07, L09-08, L10-09).
- 1 identical apart from random trace IDs (L06-04).
- L18-06: the same eighteen verdicts; its header prints the package
  version, `ch18` when captured and `appH` now.
- L05-04 differs: the rename drill now reports 3 drift problems, not
  2. The third is the gateway dashboard's panel "Time to first chunk
  p95 by provider", added after Chapter 5, which groups by
  `gen_ai_provider_name`. Chapter 5's text gives no count.
- 8 not re-run here: seven show queries against a running stack with
  data, and L01-06 needs two terminals.

Re-running `scripts/experiments.py` rewrote `experiments/latest.json`
(its version and timings only); the committed file was restored.

### Chapters 15, 18 and 19

Each was read against its plan: objective, key concepts, practical
implementation, failure scenario, tests and production lesson. All
are covered, including Chapter 15's access-controlled vault (role,
tenant and reason, every attempt logged) and the limits of replay
under non-determinism; Chapter 18's blackholing of noncritical
backends; Chapter 19's cited lifecycle, outage patterns and
blameless postmortems. No content gap was found, and no expansion
is recommended.

### GitHub Actions: pull request #1 (20 Oct 2026)

Draft pull request #1, `phase2-sync` at 3560934 into `main` at
0fb7cac, not merged. Read from the public run pages and the author's
screenshots; the step logs need a sign-in.

- compose-smoke on the pull request: Config lint, Stack smoke and
  Alert smoke succeeded. Passed.
- gates run 39418580071: Gates for this change succeeded in 49 s.
  `changed()` runs `git diff` with `check=True`, so a missing base
  fails the job rather than skipping the gates. The same command run
  locally against `origin/main` (0fb7cac), without `promtool` or the
  conventions checkout, as on the runner: contract 36 passed; drift
  38 passed, 3 skipped (two need `promtool`, one the checkout;
  compose-smoke's config lint supplies both); evaluation passed.
  Passed.
- alternatives run 39418580084, Single-container quick start (H.4):
  succeeded. The script exits 1 if any check fails, so Grafana was
  healthy, Linnet answered, and its traces and HTTP metric reached
  the bundled Tempo and Prometheus, read through Grafana. Passed;
  provider replies SIMULATED.
- alternatives run 39418580084, Jaeger v2 in place of Tempo (H.3):
  failed. The layered model validated and the stack started with
  Jaeger (44 s); the smoke step's log, from the author's screenshot:

      PASS  H.3 Linnet answers              HTTP 200 '{"answer":"Refunds reach your card within five working days.'
      FAIL  H.3 Jaeger lists linnet-api     HTTP 404, services []
      FAIL  H.3 Jaeger holds Linnet traces  HTTP 404, 0 trace(s)
      2 failed, 3 total

### Correction: the Jaeger probes use API v3 (20 Oct 2026)

Jaeger v2.21.0 (14 Sep 2026) removed the HTTP routes its UI no
longer calls, `/api/services` and the `/api/traces` search among
them (changelog: "remove v1 http endpoints the ui no longer calls",
#9260). Its API v3 serves both: `/api/v3/services`, and
`/api/v3/traces` with `query.serviceName` and a required
`query.startTimeMin`/`query.startTimeMax` window, answering OTLP
JSON, or 404 when nothing matches. Appendix H names only the UI on
port 16686, so no book text changes, and the pin stays 2.21.0.

- `scripts/smoke_alternatives.py`: the two Jaeger probes query API
  v3 and count distinct trace IDs.
- `tests/unit/test_appendices.py`: canned v3 replies, the required
  query parameters, and the 404 answer.
- Native exercise, no Docker: the Jaeger 2.21.0 release binary with
  its built-in configuration, ports shifted because the Collector
  uses the same defaults on one machine (OTLP 24317/24318, health
  23133, metrics 28888); Collector 0.162.0 with the committed
  configuration and `TEMPO_OTLP_HTTP` pointed at Jaeger; mock
  provider A and Linnet under uvicorn. `smoke_alternatives.py
  jaeger`: 3 passed (services `jaeger`, `linnet-api`; 12 traces). On
  the same Jaeger, `/api/services` and
  `/api/traces?service=linnet-api` answered 404, as in CI. No errors
  in Jaeger's log, and no trace-export errors in the Collector's
  (its metric and log exporters had no backends). Passed natively;
  the GitHub rerun is pending.
- Local checks: `pytest tests/unit tests/slo tests/resilience
  tests/drift tests/privacy`, native binaries on `PATH`: 367 passed.
  `pytest tests/lab`: 8 passed. `ruff check` and `ruff format
  --check` (254 files) and `mypy --strict src scripts tests` (223
  files): clean. `uv lock --check`: 96 packages. Listings: 130
  checked, 43 skipped, 0 missing.

### Still open in Phase 3

- The Jaeger alternative (LH-01): rerun on pull request #1 with the
  corrected probes.
- L05-04: keep it as Chapter 5's snapshot, or update its output.
- The GenAI conventions' renames since the pin: keep the pin, or move
  it under Appendix B.
