"""Configuration lint: the stack's files agree with each other.

These rules need no Docker. The CI job runs them, then validates
the Collector and Prometheus files with each component's own tool.
"""

import os
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_DIR = ROOT / "deploy" / "compose"
VERSIONS = tomllib.loads((ROOT / "versions.toml").read_text())
TELEMETRY = {
    "otel-collector",
    "prometheus",
    "tempo",
    "loki",
    "grafana",
}
APP = {"linnet-api", "mock-provider-a", "mock-provider-b", "orders"}
WRENHOLT = ("linnet-api", "orders")
COLLECTOR_ENV = {
    "TEMPO_OTLP_HTTP": "http://tempo:4318",
    "PROM_OTLP_HTTP": "http://prometheus:9090/api/v1/otlp",
    "LOKI_OTLP_HTTP": "http://loki:3100/otlp",
    # Chapter 7: the redaction processor's development key.
    "REDACTION_HMAC_KEY": "dev-only-redaction-key-not-for-production",
}


def load(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


SERVICES: dict[str, Any] = load(COMPOSE_DIR / "docker-compose.yml")[
    "services"
]


def test_both_planes_are_present() -> None:
    assert TELEMETRY | APP <= set(SERVICES)


def test_images_match_the_version_baseline() -> None:
    pinned = {
        c["image"]
        for c in VERSIONS["components"].values()
        if "image" in c
    }
    for name, service in SERVICES.items():
        if "image" in service:
            assert service["image"] in pinned, name


def test_app_image_uses_the_baseline_python_and_uv() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    python = VERSIONS["python"]["version"]
    uv = VERSIONS["packages"]["uv"]["version"]
    assert f"FROM python:{python}-slim" in dockerfile
    assert f"uv=={uv}" in dockerfile


def test_application_plane_never_waits_for_telemetry() -> None:
    for name in APP:
        waits_for = set(SERVICES[name].get("depends_on", {}))
        assert not waits_for & TELEMETRY, name


def test_wrenholt_services_export_with_a_bounded_timeout() -> None:
    for name in WRENHOLT:
        env = SERVICES[name]["environment"]
        endpoint = env["OTEL_EXPORTER_OTLP_ENDPOINT"]
        assert endpoint == "http://otel-collector:4318", name
        assert 0 < float(env["OTEL_EXPORTER_OTLP_TIMEOUT"]) <= 5, name


def test_mock_providers_export_no_telemetry() -> None:
    for name in ("mock-provider-a", "mock-provider-b"):
        env = SERVICES[name].get("environment", {})
        assert not [k for k in env if k.startswith("OTEL_")], name


def test_every_application_service_has_a_healthcheck() -> None:
    for name in APP:
        assert "healthcheck" in SERVICES[name], name


def test_collector_pipelines_protect_first_and_batch_last() -> None:
    config = load(COMPOSE_DIR / "otelcol" / "config.yaml")
    for name, pipeline in config["service"]["pipelines"].items():
        assert pipeline["receivers"] == ["otlp"], name
        assert pipeline["processors"][0] == "memory_limiter", name
        assert pipeline["processors"][-1] == "batch", name
    assert "debug" not in config["exporters"]


def test_grafana_datasources_point_at_compose_services() -> None:
    path = (
        COMPOSE_DIR
        / "grafana/provisioning/datasources/datasources.yaml"
    )
    urls = {d["uid"]: d["url"] for d in load(path)["datasources"]}
    assert urls == {
        "prometheus": "http://prometheus:9090",
        "tempo": "http://tempo:3200",
        "loki": "http://loki:3100",
    }


def test_prometheus_takes_otlp_and_scrapes_the_collector() -> None:
    assert (
        "--web.enable-otlp-receiver"
        in SERVICES["prometheus"]["command"]
    )
    config = load(COMPOSE_DIR / "prometheus" / "prometheus.yml")
    targets = [
        target
        for job in config["scrape_configs"]
        for group in job["static_configs"]
        for target in group["targets"]
    ]
    assert "otel-collector:8888" in targets


def test_jaeger_is_not_in_the_primary_stack() -> None:
    images = " ".join(
        str(s.get("image", "")) for s in SERVICES.values()
    )
    assert "jaeger" not in images


NATIVE = ROOT / ".native" / "bin" / "otelcol-contrib"
PROMTOOL = shutil.which("promtool")


@pytest.mark.skipif(not NATIVE.exists(), reason="no native Collector")
def test_collector_binary_accepts_the_config() -> None:
    config = COMPOSE_DIR / "otelcol" / "config.yaml"
    subprocess.run(
        [str(NATIVE), "validate", f"--config={config}"],
        env={**os.environ, **COLLECTOR_ENV},
        check=True,
        capture_output=True,
    )


@pytest.mark.skipif(PROMTOOL is None, reason="no promtool on PATH")
def test_promtool_accepts_the_prometheus_config() -> None:
    config = COMPOSE_DIR / "prometheus" / "prometheus.yml"
    subprocess.run(
        [str(PROMTOOL), "check", "config", str(config)],
        check=True,
        capture_output=True,
    )


def test_prometheus_stores_exemplars() -> None:
    command = SERVICES["prometheus"]["command"]
    assert "--enable-feature=exemplar-storage" in command


def test_collector_redacts_traces_and_logs() -> None:
    """Defence in depth (Chapter 7): redaction runs after the memory
    limiter and before batching, with a keyed hash."""
    path = COMPOSE_DIR / "otelcol" / "config.yaml"
    config = yaml.safe_load(path.read_text())
    redaction = config["processors"]["redaction"]
    assert redaction["hash_function"] == "hmac-sha256"
    assert redaction["hmac_key"] == "${env:REDACTION_HMAC_KEY}"
    pipelines = config["service"]["pipelines"]
    for signal in ("traces", "logs"):
        steps = pipelines[signal]["processors"]
        assert steps == ["memory_limiter", "redaction", "batch"], (
            signal
        )
