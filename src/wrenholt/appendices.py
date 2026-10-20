"""Tables for Appendices B to H, generated from the repository.

Each function reads the files the book describes, so an appendix
cannot drift from the code it documents: the pins and behaviours in
versions.toml, the registry and the pinned snapshot, the Collector
configurations and the native binary's component list, the
dashboards, the experiments, the incident code, the mock provider
and the compose file.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import yaml

from services.mock_llm.app import PROVIDER_MODELS, create_app
from services.mock_llm.faults import PLANS
from wrenholt import experiments, incidents
from wrenholt.telemetry import conventions as c
from wrenholt.telemetry.drift import load_snapshot
from wrenholt.telemetry.reference import table

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "versions.toml"
OTELCOL = ROOT / "deploy/compose/otelcol"
BINARY = ROOT / ".native/bin/otelcol-contrib"
DASHBOARDS = ROOT / "deploy/compose/grafana/provisioning/dashboards"
COMPOSE = ROOT / "deploy/compose/docker-compose.yml"


def versions() -> dict[str, Any]:
    return tomllib.loads(VERSIONS.read_text())


def code(s: object) -> str:
    return f"`{s}`"


# Appendix B ---------------------------------------------------------


def pins() -> str:
    v = versions()
    genai = v["specifications"]["genai-semconv"]
    pkg = v["packages"]
    rows = [
        ("GenAI conventions repository", genai["repository"]),
        ("Pinned commit", code(genai["commit"][:7])),
        ("Commit date", genai["commit_date"]),
        ("Status", genai["status"].split(";")[0]),
        ("Last core release with GenAI text",
         genai["last_core_release_with_genai_text"]),
        ("Core semantic conventions",
         v["specifications"]["otel-semconv"]["version"]),
    ]  # fmt: skip
    for name in (
        "opentelemetry-semantic-conventions",
        "opentelemetry-instrumentation-openai-v2",
        "opentelemetry-util-genai",
    ):
        rows.append((code(name), pkg[name]["version"]))
    return table(("Reference", "Pinned"), rows)


def package_names() -> set[str]:
    """GenAI names the pinned Python package ships."""
    names: set[str] = set()
    for mod in (
        "opentelemetry.semconv._incubating.attributes.gen_ai_attributes",
        "opentelemetry.semconv._incubating.metrics.gen_ai_metrics",
    ):
        m = importlib.import_module(mod)
        names |= {
            v
            for k, v in vars(m).items()
            if k.isupper() and isinstance(v, str)
            and v.startswith("gen_ai.")
        }  # fmt: skip
    return names


def mapping() -> str:
    snap = load_snapshot()
    spec = set(snap["attributes"]) | set(snap["metrics"])
    spec |= set(snap["events"])
    pkg = package_names()
    rows = [
        (code(n.name), n.kind, "yes" if n.name in spec else "no",
         "yes" if n.name in pkg else "no")
        for n in (*c.REGISTRY, *c.EVENTS)
        if n.source == "genai"
    ]  # fmt: skip
    return table(
        (
            "Name",
            "Kind",
            f"At {c.GENAI_COMMIT[:7]}",
            "In the package",
        ),
        rows,
    )


def gone() -> str:
    """Names the package still ships that the pinned commit no
    longer has: Wrenholt emits none of them."""
    snap = load_snapshot()
    spec = set(snap["attributes"]) | set(snap["metrics"])
    spec |= set(snap["events"]) | set(snap["spans"])
    rows = [(code(n),) for n in sorted(package_names() - spec)]
    return table(("Name in the package only",), rows)


# Appendix C ---------------------------------------------------------

KINDS = ("receivers", "processors", "exporters", "extensions",
         "connectors")  # fmt: skip


def used() -> dict[str, set[str]]:
    """Component names the three configurations use, by kind."""
    found: dict[str, set[str]] = {k: set() for k in KINDS}
    for f in sorted(OTELCOL.glob("*.yaml")):
        config = yaml.safe_load(f.read_text())
        for kind in KINDS:
            for key in config.get(kind) or {}:
                found[kind].add(key.split("/")[0])
    return found


def components() -> str:
    out = subprocess.run(
        [str(BINARY), "components"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    listed = yaml.safe_load(out)
    rows = []
    for kind, names in used().items():
        for entry in listed.get(kind) or []:
            if entry["name"] in names:
                st = entry.get("stability") or {}
                if isinstance(st, dict):
                    level = ", ".join(
                        f"{k} {v}" for k, v in sorted(st.items())
                        if v != "Undefined"
                    )  # fmt: skip
                else:
                    level = str(st)
                rows.append((kind[:-1], code(entry["name"]), level))
    return table(("Kind", "Component", "Stability at 0.162.0"), rows)


def behaviours(prefix: str = "") -> str:
    """Pinned behaviours the book relies on, as a list."""
    return "\n".join(
        f"- **{k.replace('_', ' ')}.** {undecided(v)}"
        for k, v in versions()["behaviours"].items()
        if v.startswith(prefix)
    )


def undecided(text: str) -> str:
    """Drop the plan's decision numbers, which mean nothing in
    print."""
    text = re.sub(r"\s*\(decisions? [\d, and]+\)", "", text)
    return re.sub(r";\s*decisions? [\d, and]+(?=\))", "", text)


def wrap(query: str, width: int = 66) -> str:
    """Break a query for print where whitespace is allowed: at
    spaces, and after "(", "{" and ",", never inside quotes."""
    pieces: list[tuple[str, str]] = []  # text, what follows it
    cur, quoted = "", False
    for ch in " ".join(query.split()):
        if ch == '"':
            quoted = not quoted
        if ch == " " and not quoted:
            pieces.append((cur, " "))
            cur = ""
            continue
        cur += ch
        if ch in "({," and not quoted:
            pieces.append((cur, ""))
            cur = ""
    pieces.append((cur, ""))
    lines: list[str] = []
    line = ""
    for text, sep in pieces:
        if line.strip() and len(line) + len(text) > width:
            lines.append(line.rstrip())
            line = "  "
        line += text + sep
    lines.append(line.rstrip())
    return "\n".join(lines)


# Appendix D ---------------------------------------------------------


def dashboard_queries(language: str) -> str:
    """Every query a provisioned dashboard runs, in one language:
    "prometheus" (PromQL) or "tempo" (TraceQL)."""
    rows = []
    for f in sorted(DASHBOARDS.glob("*.json")):
        board = json.loads(f.read_text())
        for p in board.get("panels", []):
            for t in p.get("targets", []):
                ds = t.get("datasource") or p.get("datasource") or {}
                kind = ds.get("type") if isinstance(ds, dict) else ""
                query = t.get("expr") or t.get("query") or ""
                if kind == language and query:
                    rows.append(
                        f"**{f.stem}: {p.get('title', '')}**"
                        f"\n\n```\n{wrap(query)}\n```"
                    )
    return "\n\n".join(rows)


# Queries no dashboard runs, for incidents: (question, query).
TRACEQL = (
    (
        "Answers that fell back to another model",
        f'{{ event:name = "{c.FALLBACK_EVENT}" }}',
    ),
    (
        "Answers served in a degraded mode",
        f"{{ span.{c.DEGRADED_MODE} != nil }}",
    ),
    (
        "Calls refused by an open breaker",
        f'{{ event:name = "{c.BREAKER_EVENT}" && '
        f'event.{c.BREAKER_STATE} = "open" }}',
    ),
    (
        "Answers from a model other than the pin",
        f"{{ span.{c.MODEL_MISMATCH} = true }}",
    ),
    (
        "Retrievals by one embedder (Chapter 15)",
        '{ span.gen_ai.operation.name = "retrieval"'
        ' && span.wrenholt.index.embedder = "wrenholt-embed-1" }',
    ),
)
LOGQL = (
    (
        "Evaluation results (Chapter 13)",
        '{service_name="linnet-api"}'
        ' | scope_name="wrenholt.evaluation"',
    ),
    (
        "Every log line of one trace",
        '{service_name="linnet-api"}'
        ' |= "4bf92f3577b34da6a3ce929d0e0e4736"',
    ),
    (
        "Reproduction bundles (Chapter 6)",
        '{service_name="linnet-api"} | wrenholt_repro_bundle != ""',
    ),
)


def listed(queries: tuple[tuple[str, str], ...]) -> str:
    return "\n\n".join(
        f"**{q}**\n\n```\n{wrap(x)}\n```" for q, x in queries
    )


# Appendix E ---------------------------------------------------------

# Scenario, injection and layer, as the plan defined them.
SCENARIOS = {
    "FS-01": ("Hidden retry storm", "429 with retry-after; SDK "
              "retries on", "L1"),
    "FS-02": ("Provider brownout", "Delay before first chunk", "L1"),
    "FS-03": ("Hard outage", "Provider A refuses connections or "
              "returns 5xx", "L1"),
    "FS-04": ("Stream cut after 200", "SSE stream ends early", "L1"),
    "FS-05": ("Malformed refund decision",
              "Invalid structured output", "L2"),
    "FS-06": ("Tool-call loop", "Model repeats order lookup", "L2"),
    "FS-07": ("Duplicate refund on retry",
              "Refund times out after commit", "L3/L4"),
    "FS-08": ("Empty retrieval after re-index",
              "Embedder version mismatch", "L3"),
    "FS-09": ("Stale return policy", "Old policy version served",
              "L3"),
    "FS-10": ("Prompt regression",
              "New prompt version raises refusals", "L3/L2"),
    "FS-11": ("Silent model change",
              "Response model differs from request", "L2"),
    "FS-12": ("Token explosion", "Verbose outputs, growing context",
              "L2/L4"),
    "FS-13": ("Costly fallback",
              "Sustained fallback to the large model", "L4"),
    "FS-14": ("PII in telemetry",
              "Email in prompt; capture misconfigured", "X"),
    "FS-15": ("Sampling blind spot",
              "Tail policy misses failing traces", "X"),
    "FS-16": ("Sale-day drift", "Intent shift plus surge", "L4/L1"),
    "FS-17": ("Guardrail over-blocking",
              "Safety filter flags refund phrasing", "L2"),
    "FS-18": ("Spend-cap exhaustion", "429 without retry-after",
              "L1/L4"),
}  # fmt: skip


def scenarios() -> str:
    latest = json.loads(
        (ROOT / "experiments/latest.json").read_text()
    )
    seen = {r["id"]: r for r in latest["results"]}
    rows = []
    for e in experiments.REGISTRY:
        name, injection, layer = SCENARIOS[e.id]
        r = seen[e.id]
        rows.append(
            (
                e.id,
                f"{name}: {injection}",
                layer,
                code(f"scripts/{e.script}.py"),
                f"{r['evidence']} ({r['verdict']})",
            )
        )
    return table(("ID", "Scenario: injection", "Layer", "Script",
                  "Last evidence"), rows)  # fmt: skip


# Appendix F ---------------------------------------------------------


def runbooks() -> str:
    """docs/runbooks.md, one heading level down, without its
    title."""
    text = (ROOT / "docs/runbooks.md").read_text()
    body = text.split("\n", 1)[1].strip("\n")
    return re.sub(r"^## ", "### ", body, flags=re.M)


def record_fields() -> str:
    rows = [
        (code(f.name), code(f.type))
        for cls in (incidents.Incident, incidents.Action)
        for f in dataclasses.fields(cls)
    ]
    return table(("Field", "Type"), rows)


def blank_postmortem() -> str:
    """The postmortem the service drafts for a new incident, before
    anyone has written a word of it."""
    i = incidents.Incident(
        "INC-0001", "availability", "SEV1", "2026-10-20T09:01:00Z"
    )
    i.note("09:01", "slo-availability-page-1h fired")
    return incidents.postmortem(i)


# Appendix G ---------------------------------------------------------


DOCS = ("/docs", "/openapi", "/redoc")  # FastAPI's own pages


def endpoints() -> str:
    from services.mock_llm.main import api

    rows = [
        (", ".join(sorted(getattr(r, "methods", None) or [])),
         code(getattr(r, "path", "")))
        for app in (create_app(), api)
        for r in app.routes
        if getattr(r, "methods", None)
        and not getattr(r, "path", "").startswith(DOCS)
    ]  # fmt: skip
    return table(("Method", "Path"), sorted(set(rows)))


def models() -> str:
    rows = [
        (p.upper(), code(alias), code(dated))
        for p, served in sorted(PROVIDER_MODELS.items())
        for alias, dated in served.items()
    ]
    return table(("Provider", "Alias", "Answers with"), rows)


def plans() -> str:
    rows = [
        (code(k), code(type(p).__name__),
         ", ".join(f"{f.name}={getattr(p, f.name)}"
                   for f in dataclasses.fields(p)))
        for k, p in PLANS.items()
    ]  # fmt: skip
    return table(("MOCK_LLM_PLAN", "Plan", "Fields"), rows)


def wrappers() -> str:
    rows = []
    for f in sorted((ROOT / "services/mock_llm").glob("*.py")):
        doc = f.read_text().split('"""')[1].split("\n\n")[0]
        doc = " ".join(doc.split())
        if f.stem not in ("__init__", "app", "main", "server"):
            rows.append((code(f.name), doc.rstrip(".")))
    return table(("Module", "What it adds"), rows)


# Appendix H ---------------------------------------------------------


def ports() -> str:
    services = yaml.safe_load(COMPOSE.read_text())["services"]
    rows = [
        (
            code(name),
            code(s.get("image", "built here")),
            ", ".join(code(p) for p in s.get("ports", [])) or "-",
        )
        for name, s in services.items()
    ]
    return table(("Service", "Image", "Host:container"), rows)


def images() -> str:
    rows = [
        (
            code(k),
            code(v.get("image") or v.get("version")),
            v.get("status", ""),
        )
        for k, v in versions()["components"].items()
        if k != "verification"
    ]
    return table(("Component", "Pinned", "Status"), rows)


def all_behaviours() -> str:
    return behaviours()


def tables() -> dict[str, str]:
    """Every generated table, by the key the appendices use."""
    return {
        "pins": pins(), "mapping": mapping(), "gone": gone(),
        "components": components(),
        "collector": behaviours("otelcol-contrib"),
        "promql": dashboard_queries("prometheus"),
        "traceql": dashboard_queries("tempo"),
        "traceql_more": listed(TRACEQL), "logql": listed(LOGQL),
        "scenarios": scenarios(), "record": record_fields(),
        "runbooks": runbooks(),
        "postmortem": blank_postmortem(), "endpoints": endpoints(),
        "models": models(), "plans": plans(), "wrappers": wrappers(),
        "ports": ports(), "images": images(),
        "behaviours": all_behaviours(),
    }  # fmt: skip
