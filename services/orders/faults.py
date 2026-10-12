"""The orders service's own fault injection, set from the environment.

ORDERS_DELAY_MS delays every request; ORDERS_FAIL_EVERY=N fails
every Nth request with HTTP 503. Both default to off.
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
    _count: int = field(default=0, init=False)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False
    )

    @classmethod
    def from_env(cls) -> "Faults":
        delay_ms = int(os.environ.get("ORDERS_DELAY_MS", "0"))
        every = int(os.environ.get("ORDERS_FAIL_EVERY", "0"))
        return cls(delay_s=delay_ms / 1000, fail_every=every)

    def apply(self) -> None:
        with self._lock:
            self._count += 1
            n = self._count
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.fail_every and n % self.fail_every == 0:
            raise HTTPException(503, "injected fault")
