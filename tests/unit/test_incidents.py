"""Incidents (Chapter 19): records, the service, the postmortem and
the game day."""

from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient

from wrenholt.api.incidents import create_app
from wrenholt.incidents import Action, Incidents, missing, postmortem
from wrenholt.labs import game_day as drill

ROOT = Path(__file__).resolve().parents[2]


def note(
    slo: str, tier: str, status: str, minute: int, fp: str = ""
) -> dict[str, Any]:
    labels = {"alertname": f"{slo} {tier}", "slo": slo,
              "severity": tier.split()[0]}  # fmt: skip
    when = f"2026-10-20T09:{minute:02d}:00+00:00"
    return {
        "status": status,
        "alerts": [
            {
                "status": status,
                "labels": labels,
                "startsAt": when,
                "endsAt": when,
                "fingerprint": fp or tier,
            }
        ],
        "groupLabels": {"slo": slo, "severity": labels["severity"]},
        "commonLabels": labels,
    }


def test_alerts_open_join_mitigate_and_reopen() -> None:
    s = Incidents()
    i = s.notify(note("availability", "page 1h", "firing", 1))
    assert (i.id, i.severity, i.status) == (
        "INC-0001",
        "SEV1",
        "open",
    )
    s.notify(note("availability", "page 1h", "firing", 2))  # repeat
    s.notify(note("availability", "ticket 3d", "firing", 5))
    assert len(s.all) == 1 and i.firing == ["page 1h", "ticket 3d"]
    s.notify(note("availability", "page 1h", "resolved", 9))
    assert i.status == "open"
    s.notify(note("availability", "ticket 3d", "resolved", 30))
    assert i.status == "mitigated"
    s.notify(note("availability", "page 1h", "firing", 40))
    assert i.status == "open"
    assert [w[1] for w in i.timeline][:3] == [
        "opened, SEV1",
        "availability page 1h fired",
        "availability ticket 3d fired",
    ]


def test_severity_follows_the_slo_and_only_rises() -> None:
    s = Incidents()
    ticket = note("groundedness", "ticket 3d", "firing", 1)
    assert s.notify(ticket).severity == "SEV3"
    page = note("decision_validity", "page 1h", "firing", 1)
    assert s.notify(page).severity == "SEV2"
    i = s.notify(note("availability", "ticket 3d", "firing", 1))
    assert i.severity == "SEV3"
    s.notify(note("availability", "page 1h", "firing", 2))
    assert (
        i.severity == "SEV1"
        and ["2026-10-20T09:02:00+00:00", "raised to SEV1"]
        in i.timeline
    )


def test_records_survive_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "incidents.json"
    s = Incidents(path)
    i = s.notify(note("availability", "page 1h", "firing", 1))
    i.actions.append(Action("Exercise the fallback", "assistant team",
                            "2026-10-27"))  # fmt: skip
    s.save()
    again = Incidents(path).all["INC-0001"]
    assert again == i


def test_the_postmortem_must_be_complete_and_anonymous() -> None:
    s = Incidents()
    i = s.notify(note("availability", "page 1h", "firing", 1))
    assert missing(postmortem(i)) == [
        "no summary", "no impact", "no root cause", "no mitigation",
        "no evidence", "no actions", "no lessons",
        "no trace evidence", "no action with an owner and a date",
    ]  # fmt: skip
    assert s.close(i) and i.status == "open"
    i.summary = (
        "Refund for WG-100006 asked by sam@example.com failed."
    )
    gaps = missing(postmortem(i))
    assert {"end-user data: email", "end-user data: order_id"} <= set(
        gaps
    )


def test_the_service_records_and_drafts() -> None:
    store = Incidents()
    with TestClient(create_app(store)) as client:
        body = note("availability", "page 1h", "firing", 1)
        assert client.post("/alerts", json=body).status_code == 204
        listed = client.get("/incidents").json()
        draft = client.get("/incidents/INC-0001/postmortem")
        nothing = client.get("/incidents/INC-0099/postmortem")
    assert [r["id"] for r in listed] == ["INC-0001"]
    assert draft.text.startswith(
        "# Postmortem INC-0001: availability"
    )
    assert nothing.status_code == 404


def test_the_game_day_closes_on_a_complete_postmortem() -> None:
    incident, before, after = drill.drill(refunds=1)
    assert (incident.severity, incident.status) == ("SEV1", "closed")
    assert len(before) == 9 and after == []
    assert [w[0][11:16] for w in incident.timeline] == [
        "09:01", "09:01", "09:02", "09:03", "09:04", "09:05",
        "09:06", "09:07", "09:11", "09:36", "15:06",
    ]  # fmt: skip
    assert incident.impact.endswith(
        "of availability's 28-day budget."
    )
    assert len(incident.traces[0]) == 32
    assert max(len(line) for line in drill.report(1)) <= 70


def test_grafana_reaches_the_incident_service_in_compose() -> None:
    compose = yaml.safe_load(
        (ROOT / "deploy/compose/docker-compose.yml").read_text()
    )
    services = compose["services"]
    url = services["grafana"]["environment"][
        "WRENHOLT_INCIDENT_WEBHOOK"
    ]
    assert url.endswith(":-http://incidents:8300/alerts}")
    assert (
        "wrenholt.api.incidents:app"
        in services["incidents"]["command"]
    )
