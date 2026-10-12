"""FS-14: a privacy scan of every exported signal.

Runs the orders service and Linnet as child processes, four times,
with a synthetic-PII workload (about thirty seconds). The fourth
run streams every answer (Chapter 8).
"""

import tempfile
from pathlib import Path

import pytest

from wrenholt.labs.fs14_lab import (
    LAB_APP,
    Scan,
    run,
    vault_check,
    workload,
)
from wrenholt.privacy.contract import FIELDS
from wrenholt.telemetry import conventions as c

ASKS = workload(3)


@pytest.fixture(scope="module")
def vault_path() -> str:
    return str(Path(tempfile.mkdtemp()) / "vault.db")


@pytest.fixture(scope="module")
def runs(vault_path: str) -> dict[str, Scan]:
    vault = {
        "WRENHOLT_CONTENT_CAPTURE": "vault",
        "WRENHOLT_VAULT_PATH": vault_path,
    }
    streamed_vault = str(Path(tempfile.mkdtemp()) / "vault.db")
    streamed = {**vault, "WRENHOLT_VAULT_PATH": streamed_vault}
    return {
        "leaky": run(LAB_APP, {"FS14_PROTECT": "0"}, ASKS),
        "protected": run(LAB_APP, {"FS14_PROTECT": "1"}, ASKS),
        "designed": run("wrenholt.api.main:app", vault, ASKS),
        "streamed": run(
            "wrenholt.api.main:app", streamed, ASKS, stream=True
        ),
    }


def test_the_misconfiguration_leaks_every_kind(
    runs: dict[str, Scan],
) -> None:
    assert all(n > 0 for n in runs["leaky"].found.values())


def test_redaction_removes_identifiers_but_not_names(
    runs: dict[str, Scan],
) -> None:
    found = runs["protected"].found
    assert found["email"] == found["phone"] == found["order_id"] == 0
    assert found["name"] > 0  # patterns cannot see names
    assert runs["protected"].redactions > 0


def test_as_designed_nothing_personal_leaves(
    runs: dict[str, Scan], vault_path: str
) -> None:
    assert sum(runs["designed"].found.values()) == 0
    assert runs["designed"].content_refs == len(ASKS)
    count, granted, denied = vault_check(vault_path)
    assert (count, granted, denied) == (len(ASKS), True, True)


def test_streamed_answers_leak_nothing(
    runs: dict[str, Scan],
) -> None:
    streamed = runs["streamed"]
    assert streamed.statuses == [200] * len(ASKS)
    assert c.STREAM_CHUNKS in streamed.keys  # the streamed path ran
    assert sum(streamed.found.values()) == 0
    assert streamed.content_refs == len(ASKS)


def test_every_exported_key_has_a_data_class(
    runs: dict[str, Scan],
) -> None:
    keys = set().union(
        *(runs[k].keys for k in ("designed", "protected", "streamed"))
    )
    assert keys - set(FIELDS) == set()


def test_tool_calls_leak_nothing(runs: dict[str, Scan]) -> None:
    # Chapter 9: every question names an order, so the agent
    # passes it to lookup_order as a tool argument.
    for name in ("designed", "streamed"):
        scan = runs[name]
        assert c.TOOL_NAME in scan.keys  # the tool ran
        assert c.TOOL_FINGERPRINT in scan.keys
        assert sum(scan.found.values()) == 0
