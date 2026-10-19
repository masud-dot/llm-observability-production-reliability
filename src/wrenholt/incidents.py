"""Incidents (Chapter 19): from the page to the postmortem.

Grafana posts every notification to the incident service, through
Chapter 14's contact point. Notifications are grouped by SLO: the
first that fires opens an incident at the severity its SLO carries,
later ones join its timeline, and when every alert has resolved the
incident is mitigated. Responders add roles, findings, evidence and
actions; an incident closes only on a complete postmortem.
"""

import bisect
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final

from wrenholt.privacy.classify import find

# A page's severity by SLO: quality and safety as well as
# availability. Tickets are SEV3.
SEVERITY: Final = {
    "availability": "SEV1",
    "ttfc_critical_action": "SEV1",
    "decision_validity": "SEV2",
    "not_refused": "SEV2",
    "ttfc_interactive": "SEV2",
    "groundedness": "SEV3",
    "policy_freshness": "SEV3",
    "answer_cost": "SEV3",
}
# Harm no objective counts, raised by a person or a scan.
SAFETY: Final = {
    "duplicate_refund": "SEV1",
    "personal_data_exported": "SEV1",
}
SECTIONS: Final = (
    "Summary", "Impact", "Timeline", "Detection", "Root cause",
    "Mitigation", "Evidence", "Actions", "Lessons",
)  # fmt: skip
TEMPO: Final = "http://localhost:3200"  # compose publishes Tempo here


@dataclass
class Action:
    what: str
    owner: str  # a team or a role, never a customer
    due: str  # ISO date


@dataclass
class Incident:
    id: str
    slo: str
    severity: str
    opened: str
    status: str = "open"  # open, mitigated or closed
    roles: dict[str, str] = field(default_factory=dict)
    timeline: list[list[str]] = field(default_factory=list)
    findings: dict[str, str] = field(default_factory=dict)  # layer
    traces: list[str] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    firing: list[str] = field(default_factory=list)  # fingerprints
    summary: str = ""
    impact: str = ""
    cause: str = ""
    mitigation: str = ""
    lessons: str = ""

    def note(self, when: str, what: str) -> None:
        bisect.insort(self.timeline, [when, what], key=lambda e: e[0])


def worse(a: str, b: str) -> str:
    return min(a, b)  # SEV1 sorts first


class Incidents:
    """The records, kept in a JSON file when given a path."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.all: dict[str, Incident] = {}
        if path is not None and path.exists():
            for raw in json.loads(path.read_text()):
                acts = [Action(**a) for a in raw.pop("actions")]
                self.all[raw["id"]] = Incident(**raw, actions=acts)

    def open_for(self, slo: str) -> Incident | None:
        live = [i for i in self.all.values() if i.slo == slo]
        live = [i for i in live if i.status != "closed"]
        return live[-1] if live else None

    def raise_(self, slo: str, severity: str, when: str) -> Incident:
        found = self.open_for(slo)
        if found is None:
            found = Incident(f"INC-{len(self.all) + 1:04d}", slo,
                             severity, when)  # fmt: skip
            self.all[found.id] = found
            found.note(when, f"opened, {severity}")
        elif worse(severity, found.severity) != found.severity:
            found.severity = severity
            found.note(when, f"raised to {severity}")
        return found

    def notify(self, body: Mapping[str, Any]) -> Incident:
        """One Grafana webhook notification."""
        labels = {**body.get("groupLabels", {}),
                  **body.get("commonLabels", {})}  # fmt: skip
        slo, tier = labels["slo"], labels.get("severity", "ticket")
        sev = SEVERITY.get(slo, "SEV3") if tier == "page" else "SEV3"
        alerts = body.get("alerts", [])
        first = alerts[0]["startsAt"] if alerts else ""
        incident = self.raise_(slo, sev, first)
        for a in alerts:
            name = a["labels"].get("alertname", tier)
            fp = a["fingerprint"]
            if a["status"] == "firing" and fp not in incident.firing:
                incident.firing.append(fp)
                incident.note(a["startsAt"], f"{name} fired")
            elif a["status"] == "resolved" and fp in incident.firing:
                incident.firing.remove(fp)
                incident.note(a["endsAt"], f"{name} resolved")
        if incident.firing and incident.status == "mitigated":
            incident.status = "open"
        elif not incident.firing and incident.status == "open":
            incident.status = "mitigated"
        self.save()
        return incident

    def close(self, incident: Incident) -> list[str]:
        """Close on a complete postmortem; else what is missing."""
        gaps = missing(postmortem(incident))
        if not gaps:
            incident.status = "closed"
            self.save()
        return gaps

    def save(self) -> None:
        if self.path is not None:
            rows = [asdict(i) for i in self.all.values()]
            self.path.write_text(json.dumps(rows, indent=1) + "\n")


def postmortem(i: Incident) -> str:
    fired = [w for w in i.timeline if w[1].endswith(" fired")]
    detection = f"{fired[0][1]} at {fired[0][0]}" if fired else ""
    body = {
        "Summary": i.summary,
        "Impact": i.impact,
        "Timeline": "\n".join(
            f"- {w} {what}" for w, what in i.timeline
        ),
        "Detection": detection,
        "Root cause": "\n".join(
            [i.cause] + [f"- {k}: {v}" for k, v in i.findings.items()]
        ).strip(),
        "Mitigation": i.mitigation,
        "Evidence": "\n".join(
            f"- [{t}]({TEMPO}/api/v2/traces/{t})" for t in i.traces
        ),
        "Actions": "\n".join(
            f"- [ ] {a.what} (owner {a.owner}, due {a.due})"
            for a in i.actions
        ),
        "Lessons": i.lessons,
    }
    head = f"# Postmortem {i.id}: {i.slo}, {i.severity}"
    roles = ", ".join(f"{k}: {v}" for k, v in i.roles.items())
    parts = [head, f"Roles: {roles}"]
    parts += [f"## {name}\n\n{body[name]}" for name in SECTIONS]
    return "\n\n".join(parts) + "\n"


def missing(text: str) -> list[str]:
    """What keeps a postmortem from being complete."""
    gaps = []
    for name in SECTIONS:
        m = re.search(
            rf"^## {name}\n(.*?)(?=^## |\Z)", text, re.M | re.S
        )
        if m is None or not m.group(1).strip():
            gaps.append(f"no {name.lower()}")
    if "/api/v2/traces/" not in text:
        gaps.append("no trace evidence")
    if not re.search(r"owner \S[^,]*, due \d{4}-\d{2}-\d{2}", text):
        gaps.append("no action with an owner and a date")
    gaps += sorted({f"end-user data: {f.kind}" for f in find(text)})
    return gaps
