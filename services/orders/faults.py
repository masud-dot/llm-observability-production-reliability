"""The orders service's own fault injection, set from the environment.

ORDERS_DELAY_MS delays every request; ORDERS_FAIL_EVERY=N fails
every Nth request with HTTP 503. ORDERS_SLOW_COMMIT_MS (Chapter 9,
FS-07) holds back the answer to a new refund after it is committed:
the caller times out, but the money has moved. All default to off.
"""

import os
import threading
import time
from dataclasses import dataclass, field

from fastapi import HTTPException


@dataclass
class Faults:
    delay_s: float = 0.0
    fail_every: int = 0
    slow_commit_s: float = 0.0
    _count: int = field(default=0, init=False)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False
    )

    @classmethod
    def from_env(cls) -> "Faults":
        delay_ms = int(os.environ.get("ORDERS_DELAY_MS", "0"))
        every = int(os.environ.get("ORDERS_FAIL_EVERY", "0"))
        slow_ms = int(os.environ.get("ORDERS_SLOW_COMMIT_MS", "0"))
        return cls(
            delay_s=delay_ms / 1000,
            fail_every=every,
            slow_commit_s=slow_ms / 1000,
        )

    def apply(self) -> None:
        with self._lock:
            self._count += 1
            n = self._count
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.fail_every and n % self.fail_every == 0:
            raise HTTPException(503, "injected fault")

    def after_commit(self) -> None:
        """FS-07: the refund is made; the answer is late."""
        if self.slow_commit_s:
            time.sleep(self.slow_commit_s)
