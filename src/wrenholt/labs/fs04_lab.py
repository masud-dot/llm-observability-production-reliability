"""FS-04 lab (Chapter 8): failures after HTTP 200 (SIMULATED).

    uv run python scripts/fs04_stream_cut.py

Linnet runs as a child process exporting to a stand-in OTLP
receiver, and the mock provider streams on a schedule that changes
for each case. Each case asks one streamed question and records
what the customer received, what the gateway's span says, what
the provider sent and what the vault kept.
"""

import json
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import httpx2

from services.mock_llm.server import running_provider
from services.mock_llm.streaming import STEADY, Schedule, Sent
from services.otlp_standin import StandIn
from services.outage_lab import Linnet, free_port
from wrenholt.privacy.vault import Reader, Vault
from wrenholt.telemetry import conventions as c

QUESTION = "When will my refund arrive?"
CASES: tuple[tuple[str, Schedule, int | None], ...] = (
    ("cut after 3 chunks", Schedule(cut_after=3), None),
    ("error event after 3 chunks", Schedule(error_after=3), None),
    ("cut before the first chunk, once",
     Schedule(cut_after=0, faulty=1), None),
    ("customer leaves after 2 chunks", STEADY, 2),
)  # fmt: skip


@dataclass(frozen=True)
class Reply:
    status: int
    events: list[tuple[str, dict[str, object]]]
    left: bool


@dataclass(frozen=True)
class Case:
    label: str
    reply: Reply
    attempts: int
    error: str | None  # error.type on the gateway's request span
    cancelled: bool
    provider: Sent
    bundle: bool  # a reproduction bundle names this request
    kept: dict[str, str]  # the vault's record of the answer


def ask(port: int, question: str, leave_after: int | None) -> Reply:
    """One streamed chat, read as server-sent events. With
    leave_after, the customer closes the connection after that many
    chunks."""
    url = f"http://127.0.0.1:{port}/chat"
    body = {"message": question, "stream": True}
    events: list[tuple[str, dict[str, object]]] = []
    kind, left = "message", False
    with httpx2.Client(timeout=15) as client:
        with client.stream("POST", url, json=body) as response:
            status = response.status_code
            for line in response.iter_lines():
                if line.startswith("event: "):
                    kind = line.removeprefix("event: ")
                elif line.startswith("data: "):
                    data = json.loads(line.removeprefix("data: "))
                    events.append((kind, data))
                    got = sum(k == "chunk" for k, _ in events)
                    if leave_after is not None and got == leave_after:
                        left = True
                        break
    return Reply(status, events, left)


def run() -> list[Case]:
    standin = StandIn(free_port())
    standin.up()
    sent: list[Sent] = []
    replies = []
    db = str(Path(tempfile.mkdtemp()) / "vault.db")
    capture = {
        "WRENHOLT_CONTENT_CAPTURE": "vault",
        "WRENHOLT_VAULT_PATH": db,
    }
    with running_provider(streaming=STEADY, sent=sent) as mock:
        assert mock.streaming is not None
        api = Linnet(
            mock.base_url, standin.port, "2", extra_env=capture
        )
        for _, schedule, leave_after in CASES:
            mock.streaming.use(schedule)
            replies.append(ask(api.port, QUESTION, leave_after))
            time.sleep(0.8)  # let the provider see a departure
        api.stop()  # flushes the spans
    standin.down()
    gateway = [
        s for s in standin.records() if s.name == "chat mock-a-fast"
    ]
    bundled = {
        json.loads(str(log.attributes[c.REPRO_BUNDLE]))["trace_id"]
        for log in standin.logs()
        if c.REPRO_BUNDLE in log.attributes
    }
    vault = Vault(db)
    who = Reader("ana", "investigator", "wrenholt")
    cases = []
    for i, (label, _, _) in enumerate(CASES):
        a = gateway[i].attributes
        kept = vault.read(gateway[i].trace_id, who, "FS-04") or {}
        error = a.get(c.ERROR_TYPE)
        cases.append(
            Case(
                label,
                replies[i],
                int(a.get(c.ATTEMPT_COUNT, 0)),
                None if error is None else str(error),
                bool(a.get(c.STREAM_CANCELLED, False)),
                # the retried case made two provider calls
                sent[-1] if i == len(CASES) - 1 else sent[i],
                gateway[i].trace_id in bundled,
                kept,
            )
        )
    return cases


def received(reply: Reply) -> str:
    chunks = sum(k == "chunk" for k, _ in reply.events)
    if reply.left:
        return f"{chunks} chunks, then closed the connection"
    last = reply.events[-1][0] if reply.events else "nothing"
    article = "an " if last == "error" else ""
    return f"{chunks} chunks, then {article}{last}"


def main() -> None:
    print("FS-04: failures after HTTP 200 (mock provider: SIMULATED)")
    for case in run():
        r, p = case.reply, case.provider
        print(case.label)
        print(f"  customer: HTTP {r.status}, {received(r)}")
        if case.cancelled:
            span = "cancelled, no error, no duration recorded"
        else:
            span = case.error or "ok"
            if case.error:
                span += f" after {p.chunks} chunks"
        print(f"  gateway:  {span}, {case.attempts} attempt"
              f"{'s' if case.attempts > 1 else ''}")  # fmt: skip
        if case.cancelled:
            print(f"  provider: stopped after {p.chunks} of "
                  f"{p.planned} chunks")  # fmt: skip
