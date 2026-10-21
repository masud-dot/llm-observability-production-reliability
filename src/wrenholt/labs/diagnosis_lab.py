"""FS-08 behind FS-02 (Chapter 15): the recorded hour and the
replay (SIMULATED).

    uv run python scripts/wrenholt_cli.py record

Linnet answers the same twelve questions twice, in process, with
the mock provider: before a re-index, then after the help-centre
index was rebuilt with a new embedder (FS-08). The spans are
recorded as they finish, keeping only registered attributes and
never content. The brownout (FS-02) began at the same time; the
mock's stream schedules give each answer's first chunk, 0.4 s
before and 3.0 s during it, added to the time Linnet spent before
calling the model. Each answer also gets its reproduction bundle.
"""

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from opentelemetry.trace import format_span_id, format_trace_id

from services.mock_llm.streaming import FS02_BROWNOUT, STEADY
from wrenholt.gateway import RetryPolicy, Route
from wrenholt.labs.agent_lab import EMBED_1, MODEL, Setup, Telemetry
from wrenholt.labs.agent_lab import ask as answer
from wrenholt.labs.cost_lab import QUESTIONS as JOURNEY
from wrenholt.labs.fs08_lab import QUESTIONS as POLICY
from wrenholt.labs.fs08_lab import Unchecked
from wrenholt.orchestrator import linnet
from wrenholt.orchestrator.prompts import Prompt
from wrenholt.privacy.vault import Reader, Vault
from wrenholt.rag.corpus import TODAY
from wrenholt.rag.embed import EMBEDDERS, Embedder
from wrenholt.rag.index import index_as_of
from wrenholt.repro import bundle
from wrenholt.slo.recorder import request_class
from wrenholt.telemetry import conventions as c

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests/fixtures/diagnosis/fs08_behind_fs02.json"
# What content capture kept (Chapter 7): the questions, SYNTHETIC,
# by trace ID. It is read only through the vault.
CAPTURED = FIXTURE.with_name("captured.json")
EMBED_2 = EMBEDDERS["wrenholt-embed-2"]
# Six policy questions, three order questions, three refunds.
HOUR = [
    *POLICY[:6],
    *[JOURNEY["order_status"]] * 3,
    *[JOURNEY["refund_request"]] * 3,
]
NAMES = {n.name for n in c.REGISTRY if n.kind == "attribute"}
SUPPORT: Prompt = vars(linnet)["SUPPORT"]


def kept(attributes: Any) -> dict[str, Any]:
    """Registered names only, and no content among them."""
    return {
        k: list(v) if isinstance(v, tuple) else v
        for k, v in dict(attributes or {}).items()
        if k in NAMES and k not in c.CONTENT
    }


def half(embedder: Embedder, first_s: float) -> list[dict[str, Any]]:
    t = Telemetry()
    index = index_as_of(TODAY, embedder)
    setup = Setup(index=index, retriever=Unchecked)
    answer(HOUR, setup, t)
    spans = t.spans.get_finished_spans()
    traces: dict[str, dict[str, Any]] = {}
    for s in spans:
        ctx = s.get_span_context()
        assert ctx is not None and s.start_time and s.end_time
        trace = traces.setdefault(
            format_trace_id(ctx.trace_id), {"spans": []}
        )
        parent = s.parent
        trace["spans"].append(
            {
                "span": format_span_id(ctx.span_id),
                "parent": format_span_id(parent.span_id)
                if parent
                else None,
                "name": s.name,
                "start_ns": s.start_time,
                "end_ns": s.end_time,
                "attributes": kept(s.attributes),
            }
        )
    out = []
    ordered = sorted(
        traces.items(),
        key=lambda kv: min(x["start_ns"] for x in kv[1]["spans"]),
    )
    for (trace_id, trace), question in zip(
        ordered, HOUR, strict=True
    ):
        trace["spans"].sort(key=lambda x: x["start_ns"])
        trace["request_class"] = request_class(question)
        trace["question"] = question  # moved to CAPTURED by record()
        start = trace["spans"][0]["start_ns"]
        chat = next(
            x for x in trace["spans"] if x["name"].startswith(c.CHAT)
        )
        before_model = (chat["start_ns"] - start) / 1e9
        trace["trace"] = trace_id
        trace["first_chunk_s"] = round(before_model + first_s, 2)
        trace["bundle"] = asdict(
            bundle(
                _context(trace_id),
                SUPPORT,
                chat["attributes"].get(c.RESPONSE_MODEL, MODEL),
                Route("wrenholt.mock_a", "http://mock", "sk-mock"),
                MODEL,
                "",
                RetryPolicy(),
                index.version,
            )
        )
        out.append(trace)
    return out


def _context(trace_id: str) -> Any:
    from opentelemetry.trace import SpanContext, TraceFlags

    return SpanContext(int(trace_id, 16), 1, False, TraceFlags(1))


def record(path: Path = FIXTURE) -> list[dict[str, Any]]:
    """Before: the old index, steady stream. After: FS-08 and
    FS-02 together."""
    traces = half(EMBED_1, STEADY.first_s)
    for t in traces:
        t["phase"] = "before"
    late = half(EMBED_2, FS02_BROWNOUT.first_s)
    for t in late:
        t["phase"] = "after"
    traces += late
    captured = {t["trace"]: {"question": t.pop("question")}
                for t in traces}  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(traces, indent=1) + "\n")
    path.with_name(CAPTURED.name).write_text(
        json.dumps(captured, indent=1) + "\n"
    )
    return traces


@dataclass(frozen=True)
class Replay:
    index_version: str
    documents: int  # passages the retriever returned
    grounded: bool  # the prompt carried at least one


def replay(
    b: Mapping[str, str], question: str, index: str = ""
) -> Replay:
    """Answer the question again against the mock with what the
    bundle names, or with another index build to test a fix."""
    if b["prompt_sha256"] != SUPPORT.sha256:
        raise ValueError("the prompt has changed since: no replay")
    version = index or b["index_version"]
    built = index_as_of(TODAY, EMBEDDERS[version.split(".", 1)[1]])
    if built.version != version:
        raise ValueError(f"no build {version} to replay against")
    t = Telemetry()
    answer([question], Setup(index=built, retriever=Unchecked), t)
    found = [s.attributes or {} for s in t.named(f"{c.RETRIEVAL} ")]
    context = [s.attributes or {} for s in t.named("build context")]
    return Replay(
        built.version,
        sum(len(a.get(c.RETRIEVAL_DOCUMENTS) or ()) for a in found),
        any(int(str(a[c.CONTEXT_TOKENS])) > 0 for a in context),
    )


def vault(path: Path = CAPTURED, tenant: str = "wrenholt") -> Vault:
    """The captured questions, behind the vault's access check."""
    v = Vault()
    for trace_id, body in json.loads(path.read_text()).items():
        v.put(trace_id, tenant, body)
    return v


def question(
    v: Vault, trace_id: str, who: Reader, reason: str
) -> str:
    body = v.read(trace_id, who, reason)
    if body is None:
        raise PermissionError(v.access_log()[-1]["outcome"])
    return body["question"]
