"""Game day (Chapter 19, SIMULATED): FS-03 and FS-07 together.

    uv run python scripts/game_day.py

Provider A refuses connections and, as in Chapter 17's opening
incident, its fallback fails too, so answers fail until a responder
moves traffic at minute 6. Refunds asked for in the outage time out
at the orders service (FS-07). The drill sends the incident service
the notifications Chapter 14's alerts would send, from its paging
lab, and the responders' steps, then checks the postmortem.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from opentelemetry.trace import format_trace_id

from wrenholt.api.incidents import create_app
from wrenholt.gateway import Route
from wrenholt.gateway.errors import ProviderError
from wrenholt.gateway.fallback import FallbackGateway
from wrenholt.gateway.retry import GuardedPolicy
from wrenholt.gateway.types import Message
from wrenholt.incidents import Action, Incident, Incidents, missing
from wrenholt.labs.agent_lab import Telemetry
from wrenholt.labs.paging_lab import ANSWERS, Scenario, run, steady

START = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
FAULT = 6  # minutes until a responder moves traffic


def at(minute: int) -> str:
    return (START + timedelta(minutes=minute)).isoformat()


def notification(
    tier: str, status: str, minute: int
) -> dict[str, Any]:
    severity = tier.split()[0]
    labels = {
        "alertname": f"availability {tier}",
        "slo": "availability",
        "severity": severity,
    }
    alert = {
        "status": status,
        "labels": labels,
        "annotations": {},
        "startsAt": at(minute),
        "endsAt": at(minute) if status == "resolved" else "",
        "fingerprint": tier.replace(" ", "-"),
    }
    group = {"slo": "availability", "severity": severity}
    return {
        "receiver": "incident-webhook",
        "status": status,
        "alerts": [alert],
        "groupLabels": group,
        "commonLabels": labels,
    }


def failed_trace() -> str:
    """One answer of the outage: A and its fallback both refuse."""
    t, nowhere = Telemetry(), "http://127.0.0.1:9/v1"
    routes = {
        "mock-a-fast": Route("wrenholt.mock_a", nowhere, "x"),
        "mock-b-standard": Route("wrenholt.mock_b", nowhere, "x"),
    }

    async def no_wait(_: float) -> None:
        pass

    async def go() -> str:
        gw = FallbackGateway(
            routes,
            GuardedPolicy(),
            tracer_provider=t.tracing,
            meter_provider=t.meters,
            sleep=no_wait,
            chains={"mock-a-fast": ["mock-b-standard"]},
        )
        tracer = t.tracing.get_tracer("wrenholt.game_day")
        try:
            with tracer.start_as_current_span("answer") as span:
                try:
                    await gw.chat(
                        "mock-a-fast", [Message("user", "Hi")]
                    )
                except ProviderError:
                    pass
                return format_trace_id(
                    span.get_span_context().trace_id
                )
        finally:
            await gw.aclose()

    return asyncio.run(go())


def respond(i: Incident, trace: str, refunds: int) -> None:
    """What the responders record, minute by minute."""
    i.roles = {
        "incident commander": "platform on-call",
        "communications": "support lead",
        "operations": "assistant on-call",
    }
    i.note(at(2), "roles assigned; status page: some answers failing")
    i.findings = {
        "L1 provider": "A refuses connections; the fallback answers"
        " 404 for a model B has retired",
        "L2 model": "no change",
        "L3 retrieval": "no change",
        "tools": "refunds timed out and were sent again with the"
        f" same key: {refunds} refund made",
    }
    i.note(at(4), "layers attributed: L1 provider")
    i.note(at(FAULT), "traffic moved to B's current model")
    i.note(at(FAULT + 1), "status page: answers are back")
    i.traces = [trace]
    i.mitigation = (
        "Traffic moved by hand to provider B's current model."
    )
    i.cause = (
        "Provider A's outage, behind a fallback never exercised."
    )
    i.lessons = (
        "The fallback failed because nothing had used it; Chapter"
        " 17's exercise would have shown it weeks before."
    )
    i.actions = [
        Action("Exercise every fallback daily", "assistant team",
               "2026-10-27"),
        Action("Add FS-03 with a broken fallback to the experiments",
               "platform team", "2026-11-03"),
    ]  # fmt: skip


def drill(refunds: int) -> tuple[Incident, list[str], list[str]]:
    paging = run(Scenario("game day", "availability",
                          steady(ANSWERS), FAULT))  # fmt: skip
    store = Incidents()
    with TestClient(create_app(store)) as client:
        sent = []
        for tier, minute in paging.fired.items():
            if minute is None:
                continue
            sent.append(
                (minute, notification(tier, "firing", minute))
            )
            back = paging.reset[tier]
            if back is not None:
                done = FAULT + back
                sent.append(
                    (done, notification(tier, "resolved", done))
                )
        for _, body in sorted(sent, key=lambda s: s[0]):
            assert (
                client.post("/alerts", json=body).status_code == 204
            )
    incident = store.all["INC-0001"]
    gaps_before = missing_now(incident)
    spent = float(paging.episode)
    incident.summary = (
        f"Answers failed for {FAULT} minutes"
        " while provider A was down."
    )
    incident.impact = f"{spent:.1%} of availability's 28-day budget."
    respond(incident, failed_trace(), refunds)
    return incident, gaps_before, store.close(incident)


def missing_now(i: Incident) -> list[str]:
    from wrenholt.incidents import postmortem

    return missing(postmortem(i))


def report(refunds: int = 1) -> list[str]:
    incident, before, after = drill(refunds)
    head = f"{incident.id}, {incident.slo}, {incident.severity}"
    lines = [f"game day: {head}"]
    lines += [
        f"  {w[11:16]}  {what}" for w, what in incident.timeline
    ]
    lines.append(
        f"postmortem from the alerts alone: {len(before)} gaps"
    )
    lines.append(f"after the responders: {len(after)} gaps,"
                 f" {incident.status}")  # fmt: skip
    return lines


def main() -> int:
    from wrenholt.labs.fs07_lab import run as fs07
    from wrenholt.tools.toolbox import Toolbox

    print("\n".join(report(len(fs07(Toolbox).refunds))))
    return 0
