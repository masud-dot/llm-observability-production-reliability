"""Appendices B to H: the generated tables and the Jaeger file."""

import re
from pathlib import Path

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
