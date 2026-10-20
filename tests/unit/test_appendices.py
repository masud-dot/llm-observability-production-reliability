"""Appendices B to H: the generated tables and the Jaeger file."""

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from services.mock_llm.streaming import Schedule
from wrenholt import appendices as a

ROOT = Path(__file__).resolve().parents[2]
NATIVE = (ROOT / ".native/bin/otelcol-contrib").exists()


def rows(t: str) -> int:
    return t.count("\n") - 1


def test_conventions_tables() -> None:
    assert "| Pinned commit | `bcc7f9c` |" in a.pins()
    assert "| Status | Development |" in a.pins()
    mapping = a.mapping()
    at_pin = [r.split(" | ")[2] for r in mapping.splitlines()[2:]]
    assert set(at_pin) == {"yes"}
    gone = a.gone()
    assert rows(gone) == 13
    assert "`gen_ai.system`" in gone and "`gen_ai.token.type`" in gone


@pytest.mark.skipif(
    not NATIVE, reason="run scripts/fetch_collector.sh"
)
def test_collector_components() -> None:
    t = a.components()
    assert rows(t) == 8
    assert "| processor | `tail_sampling` | traces Beta |" in t
    assert (
        "| exporter | `otlp_http` | logs Stable, metrics Stable," in t
    )


def test_queries_and_behaviours() -> None:
    prom, tempo = (
        a.dashboard_queries(x) for x in ("prometheus", "tempo")
    )
    assert (prom.count("**\n\n```"), tempo.count("**\n\n```")) == (
        45,
        2,
    )
    assert (len(a.TRACEQL), len(a.LOGQL)) == (5, 3)
    text = a.behaviours()
    assert "decision" not in text
    assert text.count("\n- ") + 1 == len(a.versions()["behaviours"])
    assert all(
        len(line) <= 70 or " " not in line.strip()
        for q in a.LOGQL for line in a.wrap(q[1]).splitlines()
    )  # fmt: skip


def test_scenarios_and_incidents() -> None:
    t = a.scenarios()
    assert rows(t) == 18
    assert all(f"FS-{n:02d}" in t for n in range(1, 19))
    assert len(re.findall(r"^### ", a.runbooks(), re.M)) == 8
    blank = a.blank_postmortem()
    assert len(re.findall(r"^## ", blank, re.M)) == 9
    assert "slo-availability-page-1h fired at 09:01" in blank


def test_mock_and_environment() -> None:
    assert rows(a.endpoints()) == 3
    stream = Schedule()  # G.4
    assert (stream.first_s, stream.gap_s, stream.words) == (
        0.4,
        0.12,
        1,
    )
    assert rows(a.models()) == 3 and rows(a.plans()) == 3
    assert rows(a.ports()) == 12
    jaeger = a.versions()["components"]["jaeger"]["image"]
    override = yaml.safe_load(
        (
            ROOT / "deploy/compose/docker-compose.jaeger.yml"
        ).read_text()
    )
    services = override["services"]
    assert services["jaeger"]["image"] == jaeger
    env = services["otel-collector"]["environment"]
    assert env["TEMPO_OTLP_HTTP"] == "http://jaeger:4318"
    base = yaml.safe_load(a.COMPOSE.read_text())["services"]
    assert "otel-collector" in base and "jaeger" not in base


def smoke() -> ModuleType:
    path = ROOT / "scripts/smoke_alternatives.py"
    spec = importlib.util.spec_from_file_location("alt", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_alternatives_workflow() -> None:
    path = ROOT / ".github/workflows/alternatives.yml"
    flow = yaml.safe_load(path.read_text())
    on = flow[True]  # YAML 1.1 reads "on" as True
    assert "workflow_dispatch" in on
    assert set(on["pull_request"]["paths"]) == {
        ".github/workflows/alternatives.yml",
        "deploy/compose/docker-compose.jaeger.yml",
        "scripts/smoke_alternatives.py",
    }
    jaeger, quick = flow["jobs"]["jaeger"], flow["jobs"]["quickstart"]
    assert "docker-compose.jaeger.yml" in jaeger["env"]["FILES"]
    runs = "\n".join(s.get("run", "") for s in jaeger["steps"])
    assert "smoke_alternatives.py jaeger" in runs
    lgtm = a.versions()["components"]["otel-lgtm"]["image"]
    runs = "\n".join(s.get("run", "") for s in quick["steps"])
    assert lgtm in runs and "smoke_alternatives.py lgtm" in runs


def test_alternative_probes_read_the_backends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alt = smoke()
    # Jaeger 2.21.0 answers only on API v3 (OTLP JSON traces).
    span = {"traceId": "4bf9"}
    found = {"resourceSpans": [{"scopeSpans": [{"spans": [span]}]}]}
    replies = {
        "/api/v3/services": {"services": ["linnet-api", "orders"]},
        "/api/v3/traces": {"result": found},
        "/api/datasources": [
            {"type": "tempo", "uid": "t1"},
            {"type": "prometheus", "uid": "p1"},
        ],
        "/api/datasources/proxy/uid/t1/api/search": {
            "traces": [{"traceID": "4bf9"}]
        },
        "/api/datasources/proxy/uid/p1/api/v1/query": {
            "data": {"result": [{"metric": {"job": alt.JOB}}]}
        },
    }
    asked: list[str] = []

    def fake(url: str, *_: object) -> tuple[int, str]:
        asked.append(url)
        path = url.split("//", 1)[1].split("/", 1)[1].split("?")[0]
        return 200, json.dumps(replies["/" + path])

    monkeypatch.setattr(alt, "call", fake)
    assert alt.jaeger_lists_linnet()[0]
    assert alt.jaeger_has_traces()[0]
    assert alt.lgtm_has_traces()[0]
    assert alt.lgtm_has_metric()[0]
    assert any(
        "job%3D%22wrenholt%2Flinnet-api%22" in u for u in asked
    )
    traces = next(u for u in asked if "/api/v3/traces?" in u)
    keys = ("serviceName=linnet-api", "startTimeMin", "startTimeMax")
    assert all(f"query.{k}" in traces for k in keys)
    gone = json.dumps({"error": {"message": "No traces found"}})
    monkeypatch.setattr(alt, "call", lambda *_: (404, gone))
    assert alt.jaeger_has_traces() == (False, "HTTP 404, 0 trace(s)")
