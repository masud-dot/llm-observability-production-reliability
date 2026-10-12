"""The content vault (Chapter 7): content by reference.

Stores a question and its answer only when capture is on, for a
limited time. Every read is logged, granted or not, and the log
never holds content. Only investigators of the same tenant read.
"""

import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass

# The only tier that reads content.
READERS = frozenset({"investigator"})
SCHEMA = """
CREATE TABLE IF NOT EXISTS content (
    ref TEXT PRIMARY KEY, trace_id TEXT, tenant TEXT,
    expires REAL, body TEXT);
CREATE TABLE IF NOT EXISTS access (
    at REAL, reader TEXT, role TEXT, key TEXT, reason TEXT,
    outcome TEXT);
"""


@dataclass(frozen=True)
class Reader:
    name: str
    role: str
    tenant: str


class Vault:
    def __init__(
        self,
        path: str = ":memory:",
        ttl_s: float = 72 * 3600,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self._ttl, self._clock = ttl_s, clock
        with self._lock:
            self._db.executescript(SCHEMA)

    def put(
        self, trace_id: str, tenant: str, body: Mapping[str, str]
    ) -> str:
        ref = f"vault:{uuid.uuid4().hex}"
        expires = self._clock() + self._ttl
        row = (ref, trace_id, tenant, expires, json.dumps(dict(body)))
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO content VALUES (?,?,?,?,?)", row
            )
        return ref

    def read(
        self, key: str, reader: Reader, reason: str
    ) -> dict[str, str] | None:
        """By reference or trace ID. Every attempt is logged."""
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT tenant, expires, body FROM content"
                " WHERE ref = ? OR trace_id = ?",
                (key, key),
            ).fetchone()
            if reader.role not in READERS or not reason:
                outcome = "denied: role or reason"
            elif row is None:
                outcome = "missing"
            elif row[0] != reader.tenant:
                outcome = "denied: tenant"
            elif row[1] <= self._clock():
                outcome = "expired"
            else:
                outcome = "granted"
            self._db.execute(
                "INSERT INTO access VALUES (?,?,?,?,?,?)",
                (
                    self._clock(),
                    reader.name,
                    reader.role,
                    key,
                    reason,
                    outcome,
                ),
            )
        if outcome != "granted":
            return None
        found: dict[str, str] = json.loads(row[2])
        return found

    def stored(self) -> list[str]:
        """Trace IDs with content in the vault; never the content."""
        with self._lock:
            rows = self._db.execute("SELECT trace_id FROM content")
            return [str(r[0]) for r in rows.fetchall()]

    def purge(self) -> int:
        with self._lock, self._db:
            cur = self._db.execute(
                "DELETE FROM content WHERE expires <= ?",
                (self._clock(),),
            )
        return int(cur.rowcount)

    def access_log(self) -> list[dict[str, object]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM access").fetchall()
        keys = ("at", "reader", "role", "key", "reason", "outcome")
        return [dict(zip(keys, r, strict=True)) for r in rows]
