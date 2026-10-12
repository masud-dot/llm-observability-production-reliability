"""Request context the gateway reads (Chapter 6): which prompt the
caller used. Set by the orchestrator around a call."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

PROMPT: ContextVar[tuple[str, str] | None] = ContextVar(
    "wrenholt_prompt", default=None
)


@contextmanager
def prompt(name: str, version: str) -> Iterator[None]:
    token = PROMPT.set((name, version))
    try:
        yield
    finally:
        PROMPT.reset(token)
