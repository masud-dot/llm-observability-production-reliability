# Chapter verification targets. Without make (for example in Git
# Bash on Windows), run the commands under a target one by one.
.PHONY: verify-ch01 fs01 verify-ch02 fs09 verify-ch03 outage verify-ch04 gateway-lab verify-ch05 rename-drill names-lab semconv-snapshot verify-ch06 correlation-lab fs11 verify-ch07 fs14 hash-lab verify-ch08 fs02 fs04 verify-ch09 fs06 fs07 fs08 verify-ch10 fetch-collector fs15 overload verify-ch11 fs12 fs13 verify-ch12 slo-rules fs05 fs17 verify-ch13 fs10 fs09-index fs16

verify-ch01:
	uv sync --group dev --group lab
	uv run ruff check src services scripts tests
	uv run ruff format --check src services/mock_llm tests \
		scripts/fs01_hidden_retry.py
	uv run mypy src services scripts tests
	uv run --group lab pytest tests/unit tests/lab
	uv run --group lab python scripts/fs01_hidden_retry.py

fs01:
	uv run --group lab python scripts/fs01_hidden_retry.py

verify-ch02:
	uv sync --group dev --group lab
	uv run ruff check src services scripts tests
	uv run ruff format --check src/wrenholt/slo tests/slo \
		scripts/fs09_sli_report.py
	uv run mypy src services scripts tests
	uv run --group lab pytest tests/unit tests/lab tests/slo
	uv run python scripts/fs09_sli_report.py

fs09:
	uv run python scripts/fs09_sli_report.py

verify-ch03:
	uv sync --group dev --group lab
	uv run ruff check src services scripts tests
	uv run ruff format --check src/wrenholt/telemetry src/wrenholt/api services/orders services/serving.py services/otlp_standin.py services/outage_lab.py services/noflush_app.py services/healthcheck.py scripts/collector_outage.py scripts/smoke_wrenholt.py tests/unit/test_config_lint.py tests/unit/test_orders_service.py tests/unit/test_mock_provider_b.py tests/unit/test_telemetry_setup.py tests/resilience
	uv run mypy src services scripts tests
	uv run pytest tests/unit tests/slo tests/resilience
	uv run --group lab pytest tests/lab
	uv run python scripts/collector_outage.py

outage:
	uv run python scripts/collector_outage.py

verify-ch04:
	uv sync --group dev --group lab
	uv run ruff check src services scripts tests
	uv run ruff format --check src/wrenholt/gateway src/wrenholt/telemetry src/wrenholt/orchestrator/linnet.py src/wrenholt/api src/wrenholt/labs/gateway_lab.py services/mock_llm/spend_cap.py services/mock_llm/server.py services/mock_llm/main.py services/outage_lab.py scripts/gateway_lab.py scripts/collector_outage.py tests/unit/test_error_map.py tests/unit/test_gateway_contract.py tests/lab tests/resilience
	uv run --group lab mypy src services scripts tests
	uv run pytest tests/unit tests/slo tests/resilience
	uv run --group lab pytest tests/lab
	uv run --group lab python scripts/gateway_lab.py

gateway-lab:
	uv run --group lab python scripts/gateway_lab.py

verify-ch05:
	uv sync --group dev --group lab
	uv run ruff check src services scripts tests
	uv run ruff format --check src services scripts tests
	uv run --group lab mypy src services scripts tests
	uv run pytest tests/unit tests/slo tests/resilience tests/drift
	uv run --group lab pytest tests/lab
	uv run python scripts/rename_drill.py
	uv run --group lab python scripts/names_lab.py

rename-drill:
	uv run python scripts/rename_drill.py

names-lab:
	uv run --group lab python scripts/names_lab.py

# Needs a checkout of the GenAI repository at conventions.GENAI_COMMIT.
semconv-snapshot:
	uv run python scripts/semconv_snapshot.py $(SEMCONV_GENAI_DIR)

verify-ch06:
	uv sync --group dev --group lab
	uv run ruff check src services scripts tests
	uv run ruff format --check src services scripts tests
	uv run --group lab mypy src services scripts tests
	uv run pytest tests/unit tests/slo tests/resilience tests/drift
	uv run --group lab pytest tests/lab
	uv run python scripts/correlation_lab.py
	uv run python scripts/fs11_model_change.py

correlation-lab:
	uv run python scripts/correlation_lab.py

fs11:
	uv run python scripts/fs11_model_change.py

verify-ch07:
	uv sync --group dev --group lab
	uv run ruff check src services scripts tests
	uv run ruff format --check src services scripts tests
	uv run --group lab mypy src services scripts tests
	uv run pytest tests/unit tests/slo tests/resilience tests/drift tests/privacy
	uv run --group lab pytest tests/lab
	uv run python scripts/fs14_pii.py
	uv run python scripts/hash_reversal.py

fs14:
	uv run python scripts/fs14_pii.py

hash-lab:
	uv run python scripts/hash_reversal.py

verify-ch08:
	uv sync --group dev --group lab
	uv run ruff check src services scripts tests
	uv run ruff format --check src services scripts tests
	uv run --group lab mypy src services scripts tests
	uv run pytest tests/unit tests/slo tests/resilience tests/drift tests/privacy
	uv run --group lab pytest tests/lab
	uv run python scripts/fs02_brownout.py
	uv run python scripts/fs04_stream_cut.py

fs02:
	uv run python scripts/fs02_brownout.py

fs04:
	uv run python scripts/fs04_stream_cut.py

verify-ch09:
	uv sync --group dev --group lab
	uv run ruff check src services scripts tests
	uv run ruff format --check src services scripts tests
	uv run --group lab mypy src services scripts tests
	uv run pytest tests/unit tests/slo tests/resilience tests/drift tests/privacy
	uv run --group lab pytest tests/lab
	uv run python scripts/fs06_tool_loop.py
	uv run python scripts/fs07_duplicate_refund.py
	uv run python scripts/fs08_empty_retrieval.py

fs06:
	uv run python scripts/fs06_tool_loop.py

fs07:
	uv run python scripts/fs07_duplicate_refund.py

fs08:
	uv run python scripts/fs08_empty_retrieval.py

verify-ch10:
	uv sync --group dev --group lab
	scripts/fetch_collector.sh
	uv run ruff check src services scripts tests
	uv run ruff format --check src services scripts tests
	uv run --group lab mypy src services scripts tests
	uv run pytest tests/unit tests/slo tests/resilience tests/drift tests/privacy
	uv run --group lab pytest tests/lab
	uv run python scripts/fs15_sampling_blind_spot.py
	uv run python scripts/collector_overload.py

fetch-collector:
	scripts/fetch_collector.sh

fs15:
	uv run python scripts/fs15_sampling_blind_spot.py

overload:
	uv run python scripts/collector_overload.py

verify-ch11:
	uv sync --group dev --group lab
	scripts/fetch_collector.sh
	uv run ruff check src services scripts tests
	uv run ruff format --check src services scripts tests
	uv run --group lab mypy src services scripts tests
	uv run pytest tests/unit tests/slo tests/resilience tests/drift tests/privacy
	uv run --group lab pytest tests/lab
	uv run python scripts/fs12_token_explosion.py
	uv run python scripts/fs13_costly_fallback.py

fs12:
	uv run python scripts/fs12_token_explosion.py

fs13:
	uv run python scripts/fs13_costly_fallback.py

verify-ch12:
	uv sync --group dev --group lab
	scripts/fetch_collector.sh
	uv run ruff check src services scripts tests
	uv run ruff format --check src services scripts tests
	uv run --group lab mypy src services scripts tests
	uv run pytest tests/unit tests/slo tests/resilience tests/drift tests/privacy
	uv run --group lab pytest tests/lab
	uv run python scripts/fs05_malformed_refund.py
	uv run python scripts/fs17_over_blocking.py

slo-rules:
	uv run python scripts/slo_rules.py

fs05:
	uv run python scripts/fs05_malformed_refund.py

fs17:
	uv run python scripts/fs17_over_blocking.py

verify-ch13:
	uv sync --group dev --group lab
	scripts/fetch_collector.sh
	uv run ruff check src services scripts tests
	uv run ruff format --check src services scripts tests
	uv run --group lab mypy src services scripts tests
	uv run pytest tests/unit tests/slo tests/resilience tests/drift tests/privacy
	uv run --group lab pytest tests/lab
	uv run python scripts/fs10_prompt_regression.py
	uv run python scripts/fs09_index_swap.py
	uv run python scripts/fs16_intent_drift.py

fs10:
	uv run python scripts/fs10_prompt_regression.py

fs09-index:
	uv run python scripts/fs09_index_swap.py

fs16:
	uv run python scripts/fs16_intent_drift.py
