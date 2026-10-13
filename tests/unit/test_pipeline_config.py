"""The production-like Collector profile (Chapter 10).

The numbers in config.production.yaml come from a planning figure,
the request deadline, the SDK's defaults and what Chapter 10's
native run measured. These tests keep them in step, and keep the
sampling policies in step with the coverage map in sampling.py.
"""

import os
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from wrenholt.labs import fs15_lab
from wrenholt.slo.fs09 import normal_hour
from wrenholt.slo.request_map import load_request_map
from wrenholt.telemetry import conventions as c
from wrenholt.telemetry import drift
from wrenholt.telemetry.sampling import (
    BASELINE,
    BASELINE_PERCENT,
    KEEP,
    POLICIES,
)

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "compose"
OTELCOL = COMPOSE / "otelcol"
BOARD = COMPOSE / "grafana/provisioning/dashboards/llm-gateway.json"

# The planning figure, and what one answer costs (native run,
# Chapter 10): two traces, and these spans by journey.
PEAK = 40  # answers a second at a sale-day peak
TRACES = 2  # the request's and its reproduction bundle's
SPANS = {"policy_question": 9, "order_status": 18,
         "refund_request": 24}  # fmt: skip
LOG_RECORDS = 2  # "chat answered" and the reproduction bundle
EXPORT_INTERVAL_S = 5.0  # linnet-api's, set in Compose


def load(name: str) -> Any:
    return yaml.safe_load((OTELCOL / name).read_text())


PRODUCTION = load("config.production.yaml")
SAMPLING = PRODUCTION["processors"]["tail_sampling"]
QUEUES = {
    name: e["sending_queue"]
    for name, e in PRODUCTION["exporters"].items()
}


def seconds(value: str) -> float:
    found = re.fullmatch(r"(\d+)(ms|s)", value)
    assert found, value
    number, unit = found.groups()
    return int(number) / (1000 if unit == "ms" else 1)


def test_spans_per_answer_on_the_normal_hour() -> None:
    hour = [event.journey for event in normal_hour()]
    spans = sum(SPANS[journey] for journey in hour) / len(hour)
    assert (len(hour), spans) == (120, 15)


def test_the_processors_run_in_order() -> None:
    pipelines = PRODUCTION["service"]["pipelines"]
    assert pipelines["traces"]["processors"] == [
        "memory_limiter", "redaction", "tail_sampling", "batch",
    ]  # fmt: skip
    assert pipelines["metrics"]["processors"] == [
        "memory_limiter", "batch",
    ]  # fmt: skip
    assert pipelines["logs"]["processors"] == [
        "memory_limiter", "redaction", "batch",
    ]  # fmt: skip


def test_both_profiles_redact_alike() -> None:
    development = load("config.yaml")["processors"]["redaction"]
    assert PRODUCTION["processors"]["redaction"] == development


def test_the_policies_are_the_coverage_maps() -> None:
    found = []
    for p in SAMPLING["policies"]:
        settings = p[p["type"]]
        key = settings.get("key", "")
        if p["type"] == "ottl_condition":
            (condition,) = settings["span"]
            (key,) = re.findall(r'attributes\["([^"]+)"\]', condition)
        values = tuple(settings.get("values", ()))
        found.append((p["name"], p["type"], key, values))
    expected = [(p.name, p.type, p.key, p.values) for p in POLICIES]
    assert found == expected


def test_every_policy_key_is_registered() -> None:
    names = {n.name for n in c.REGISTRY if n.kind == "attribute"}
    assert {p.key for p in POLICIES if p.key} <= names


def test_every_gateway_panel_names_the_traces_behind_it() -> None:
    titles = [
        p["title"]
        for p in yaml.safe_load(BOARD.read_text())["panels"]
    ]
    assert sorted(k.panel for k in KEEP) == sorted(titles)
    assert {k.policy for k in KEEP} <= {p.name for p in POLICIES}


def test_thresholds_match_the_slis_and_the_deadline() -> None:
    policies = {p["name"]: p for p in SAMPLING["policies"]}
    slow_first = policies["slow-first-chunk"]["ottl_condition"]
    (condition,) = slow_first["span"]
    assert condition.endswith(f">= {c.SLI_THRESHOLDS[0]}")
    deadline_ms = load_request_map().deadline_s * 1000
    assert policies["slow"]["latency"]["threshold_ms"] == deadline_ms
    baseline = policies[BASELINE]["probabilistic"]
    assert baseline["sampling_percentage"] == BASELINE_PERCENT == 10


def test_every_span_is_in_before_the_decision() -> None:
    services = yaml.safe_load(
        (COMPOSE / "docker-compose.yml").read_text()
    )["services"]
    for name in ("linnet-api", "orders"):
        env = services[name]["environment"]
        # The SDK's default when Compose leaves it unset: 5000 ms.
        delay = float(env.get("OTEL_BSP_SCHEDULE_DELAY", 5000)) / 1000
        deadline = load_request_map().deadline_s
        assert deadline + delay <= seconds(SAMPLING["decision_wait"])


def test_no_trace_is_dropped_undecided_at_the_peak() -> None:
    rate = SAMPLING["expected_new_traces_per_sec"]
    assert rate == PEAK * TRACES == 80
    in_one_wait = rate * seconds(SAMPLING["decision_wait"])
    assert in_one_wait == 1600
    assert SAMPLING["num_traces"] >= 3 * in_one_wait
    cache = SAMPLING["decision_cache"]["sampled_cache_size"]
    assert cache / rate >= 20 * 60  # twenty minutes at the peak


def test_the_queues_hold_what_their_comment_says() -> None:
    assert {q["sizer"] for q in QUEUES.values()} == {"items"}
    hour = [event.journey for event in normal_hour()]
    mix = sum(SPANS[j] for j in hour) / len(hour)
    assert QUEUES["otlp_http/tempo"]["queue_size"] >= PEAK * mix * 60
    assert QUEUES["otlp_http/tempo"]["queue_size"] == 36000
    records = PEAK * LOG_RECORDS * 120
    assert QUEUES["otlp_http/loki"]["queue_size"] >= records == 9600
    points = sum(b.combinations for b in c.BUDGET)  # per export
    exports = 5 * 60 / EXPORT_INTERVAL_S
    queue = QUEUES["otlp_http/prometheus"]["queue_size"]
    assert queue >= points * exports == 151 * 60


def test_the_export_interval_is_the_one_compose_sets() -> None:
    services = yaml.safe_load(
        (COMPOSE / "docker-compose.yml").read_text()
    )["services"]
    env = services["linnet-api"]["environment"]
    interval = float(env["OTEL_METRIC_EXPORT_INTERVAL"]) / 1000
    assert interval == EXPORT_INTERVAL_S
    # Cumulative, the SDK's default: a later export restores totals.
    preference = "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE"
    assert preference not in env


def test_no_config_uses_the_deprecated_alias() -> None:
    for path in OTELCOL.glob("*.yaml"):
        text = path.read_text()
        for line in text.splitlines():
            if not line.lstrip().startswith("#"):
                assert "otlphttp" not in line, path.name
                assert "loadbalancing:" not in line, path.name


def test_the_first_tier_routes_whole_traces() -> None:
    tier = load("loadbalancing.yaml")
    exporter = tier["exporters"]["load_balancing"]
    assert exporter["routing_key"] == "traceID"
    # Off by default: re-route when a sampler goes away.
    assert exporter["retry_on_failure"]["enabled"] is True
    assert exporter["sending_queue"]["enabled"] is True
    assert "tail_sampling" not in tier["processors"]
    assert list(tier["service"]["pipelines"]) == ["traces"]


def test_gomemlimit_is_80_per_cent_of_the_limit() -> None:
    override = yaml.safe_load(
        (COMPOSE / "docker-compose.production.yml").read_text()
    )["services"]["otel-collector"]
    limit = PRODUCTION["processors"]["memory_limiter"]["limit_mib"]
    gomemlimit = override["environment"]["GOMEMLIMIT"]
    assert gomemlimit == f"{int(limit * 0.8)}MiB" == "320MiB"
    mounted = override["volumes"][0]["target"]
    assert override["command"] == [f"--config={mounted}"]


def test_the_labs_read_names_in_the_collector_snapshot() -> None:
    names = set(drift.load_collector_snapshot())
    assert {fs15_lab.DECIDED, fs15_lab.VOTES} <= names
    assert {
        "otelcol_receiver_refused_spans",
        "otelcol_exporter_enqueue_failed_spans",
    } <= names  # read by the overload lab


def test_the_fetch_script_pins_the_recorded_hashes() -> None:
    script = (ROOT / "scripts" / "fetch_collector.sh").read_text()
    pattern = r"(\w+_\w+)\)\n\s+want=([0-9a-f]{64})"
    found = dict(re.findall(pattern, script))
    versions = tomllib.loads((ROOT / "versions.toml").read_text())
    pinned = versions["components"]["otelcol-contrib-binary"]
    assert found == {
        key.removeprefix("sha256_"): value
        for key, value in pinned.items()
        if key.startswith("sha256_")
    }
    assert f'VERSION="{pinned["version"]}"' in script


NATIVE = ROOT / ".native" / "bin" / "otelcol-contrib"
ENV = {
    "TEMPO_OTLP_HTTP": "http://tempo:4318",
    "PROM_OTLP_HTTP": "http://prometheus:9090/api/v1/otlp",
    "LOKI_OTLP_HTTP": "http://loki:3100/otlp",
    "REDACTION_HMAC_KEY": "dev-only-redaction-key-not-for-production",
}


@pytest.mark.skipif(not NATIVE.exists(), reason="no native Collector")
@pytest.mark.parametrize(
    "name", ["config.production.yaml", "loadbalancing.yaml"]
)
def test_the_collector_accepts_the_config(name: str) -> None:
    subprocess.run(
        [str(NATIVE), "validate", f"--config={OTELCOL / name}"],
        env={**os.environ, **ENV},
        check=True,
        capture_output=True,
    )
