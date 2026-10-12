"""Serve an ASGI app on a free local port, in a thread (tests)."""

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import uvicorn
from fastapi import FastAPI


@contextmanager
def serve(app: FastAPI) -> Iterator[str]:
    """Yield the base URL while the app runs."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port: int = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [sock]}, daemon=True
    )
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("app did not start")
        time.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
