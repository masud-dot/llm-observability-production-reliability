"""FS-14 lab (Chapter 7): PII in telemetry (SIMULATED workload).

    uv run python scripts/fs14_pii.py

Questions built from the orders dataset carry a customer's name,
email, phone number and order ID. Three configurations answer the
same questions; a scan reads every exported span, log record and
metric, and both services' stdout, for each kind of personal data.
"""

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from services.mock_llm.server import running_provider
from services.mock_llm.streaming import STEADY
from services.orders.store import generate_orders
from services.otlp_standin import StandIn
from services.outage_lab import Linnet, free_port
from wrenholt.labs.fs04_lab import ask as ask_streamed
from wrenholt.privacy.vault import Reader, Vault
from wrenholt.telemetry import conventions as c

KINDS = ("email", "phone", "order_id", "name")
FAST = {"OTEL_METRIC_EXPORT_INTERVAL": "1000"}


def workload(count: int = 10) -> list[dict[str, str]]:
    asks = []
    for o in generate_orders()[6 : 6 + count]:
        question = (
            f"Hi, I'm {o.customer} ({o.email}, {o.phone}). "
            f"Where is order {o.order_id}?"
        )
        asks.append(
            {
                "name": o.customer,
                "email": o.email,
                "phone": o.phone,
                "order_id": o.order_id,
                "question": question,
            }
        )
    return asks


@dataclass(frozen=True)
class Scan:
    found: dict[str, int]  # kind: exported values that hold one
    redactions: int
    keys: set[str]  # every attribute key exported
    content_refs: int
    statuses: list[int]


def exported(
    standin: StandIn,
) -> tuple[list[str], set[str], int, int]:
    """Every exported string, every attribute key, the redaction
    count and how many server spans carry a content reference."""
    values: list[str] = []
    keys: set[str] = set()
    refs = 0
    for s in standin.records():
        values.append(s.name)
        values += [
            str(v)
            for v in (*s.attributes.values(), *s.resource.values())
        ]
        keys |= set(s.attributes)
        refs += c.CONTENT_REF in s.attributes
    for log in standin.logs():
        values.append(log.body)
        values += [str(v) for v in log.attributes.values()]
        keys |= set(log.attributes)
    last: dict[tuple[str, str], float] = {}
    for p in standin.points():
        values += [str(v) for v in p.attributes.values()]
        keys |= set(p.attributes)
        if p.name == c.REDACTIONS:
            last[(p.service, repr(sorted(p.attributes.items())))] = (
                p.value
            )
    return values, keys, int(sum(last.values())), refs


def scan(
    values: list[str], asks: list[dict[str, str]]
) -> dict[str, int]:
    return {
        kind: sum(any(a[kind] in v for a in asks) for v in values)
        for kind in KINDS
    }


def run(
    target: str,
    env: dict[str, str],
    asks: list[dict[str, str]],
    stream: bool = False,
) -> Scan:
    """One configuration. With stream, every question is asked
    for a streamed answer (Chapter 8)."""
    standin = StandIn(free_port())
    standin.up()
    schedule = STEADY if stream else None
    with running_provider(streaming=schedule) as mock:
        orders = Linnet(
            mock.base_url, standin.port, "2",
            "services.orders.main:app", name="orders", extra_env=FAST,
        )  # fmt: skip
        url = f"http://127.0.0.1:{orders.port}"
        api = Linnet(
            mock.base_url, standin.port, "2", target,
            extra_env={"WRENHOLT_ORDERS_URL": url, **FAST, **env},
        )  # fmt: skip
        if stream:
            statuses = [
                ask_streamed(api.port, a["question"], None).status
                for a in asks
            ]
        else:
            statuses = [api.ask(a["question"])[0] for a in asks]
        time.sleep(2.5)  # one metric interval and one batch delay
        api.stop()
        orders.stop()
    standin.down()
    values, keys, redactions, refs = exported(standin)
    values += api.log.read_text().splitlines()
    values += orders.log.read_text().splitlines()
    return Scan(scan(values, asks), redactions, keys, refs, statuses)


def vault_check(path: str) -> tuple[int, bool, bool]:
    vault = Vault(path)
    stored = vault.stored()
    who = Reader("ana", "investigator", "wrenholt")
    granted = vault.read(stored[0], who, "FS-14 review") is not None
    bo = Reader("bo", "on-call", "wrenholt")
    denied = vault.read(stored[0], bo, "curious") is None
    return len(stored), granted, denied


LAB_APP = "wrenholt.labs.fs14_app:app"


def main() -> None:
    asks = workload()
    db = str(Path(tempfile.mkdtemp()) / "vault.db")
    vault_env = {
        "WRENHOLT_CONTENT_CAPTURE": "vault",
        "WRENHOLT_VAULT_PATH": db,
    }
    configs = {
        "misconfigured": (LAB_APP, {"FS14_PROTECT": "0"}),
        "misconfigured, protected": (LAB_APP, {"FS14_PROTECT": "1"}),
        "as designed, vault": ("wrenholt.api.main:app", vault_env),
    }
    print("FS-14: PII in telemetry (mock provider: SIMULATED)")
    print(
        f"{len(asks)} questions with a name, email, phone and order"
    )
    head = f"{'':<26}{'email':>6}{'phone':>6}{'order':>6}{'name':>6}"
    print(head + f"{'redacted':>10}")
    for label, (target, env) in configs.items():
        r = run(target, env, asks)
        f = r.found
        row = f"{label:<26}{f['email']:>6}{f['phone']:>6}"
        row += f"{f['order_id']:>6}{f['name']:>6}{r.redactions:>10}"
        print(row)
    count, granted, denied = vault_check(db)
    print(f"vault: {count} records, by reference")
    print(f"  investigator read granted: {granted}")
    print(f"  on-call read denied: {denied}")
