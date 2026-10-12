"""Run the mock provider in a background thread (tests, labs)."""

import socket
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import uvicorn

from services.mock_llm.app import ProviderLog, create_app
from services.mock_llm.faults import NO_FAULTS, FaultPlan
from services.mock_llm.headers import with_header_log
from services.mock_llm.model_swap import with_model_swap
from services.mock_llm.spend_cap import with_spend_cap
from services.mock_llm.streaming import Schedule, Sent, Streaming


@dataclass(frozen=True)
class RunningProvider:
    base_url: str
    log: ProviderLog
    streaming: Streaming | None = None  # Chapter 8


@contextmanager
def running_provider(
    plan: FaultPlan = NO_FAULTS,
    *,
    spend_cap: bool = False,
    model_swap: Mapping[str, str] | None = None,
    headers: list[dict[str, str]] | None = None,
    streaming: Schedule | None = None,
    sent: list[Sent] | None = None,
) -> Iterator[RunningProvider]:
    log = ProviderLog()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port: int = sock.getsockname()[1]
    app = create_app(plan, log)
    if spend_cap:  # FS-18 (Chapter 4)
        app = with_spend_cap(app, log)
    if model_swap is not None:  # FS-11 (Chapter 6); may change later
        app = with_model_swap(app, model_swap)
    if headers is not None:  # what reaches the provider (Chapter 6)
        app = with_header_log(app, headers)
    served: Any = app
    wrapper = None
    if streaming is not None:  # SSE on a schedule (Chapter 8)
        served = wrapper = Streaming(app, streaming, sent)
    server = uvicorn.Server(
        uvicorn.Config(served, log_level="warning")
    )
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [sock]}, daemon=True
    )
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("mock provider did not start")
        time.sleep(0.01)
    try:
        url = f"http://127.0.0.1:{port}/v1"
        yield RunningProvider(url, log, wrapper)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
