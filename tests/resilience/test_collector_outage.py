"""Collector outage: customers keep being served; telemetry pays.

Short versions of scripts/collector_outage.py, asserted. Linnet
runs as a child process exporting to a stand-in OTLP receiver.
"""

import signal
import time
from collections.abc import Iterator

import pytest

from services.mock_llm.server import running_provider
from services.otlp_standin import StandIn
from services.outage_lab import REQUEST_SPAN, Linnet, free_port

NO_FLUSH = "services.noflush_app:app"


@pytest.fixture(scope="module")
def provider() -> Iterator[str]:
    with running_provider() as running:
        yield running.base_url


def test_linnet_serves_through_refused_and_hung_exports(
    provider: str,
) -> None:
    standin = StandIn(free_port())
    standin.up()
    api = Linnet(provider, standin.port, "2")
    try:
        for mode in ("down", "hang"):
            getattr(standin, mode)()
            results = [api.chat() for _ in range(10)]
            assert [status for status, _ in results] == [200] * 10
            assert max(seconds for _, seconds in results) < 1.0
            time.sleep(1.5)  # let an export attempt fail or hang
        standin.up()
        start = time.time_ns()
        assert [api.chat()[0] for _ in range(10)] == [200] * 10
        time.sleep(4)
        late = [
            s
            for s, _, name in standin.spans()
            if s >= start and name == REQUEST_SPAN
        ]
        assert len(late) == 10  # telemetry resumes after recovery
    finally:
        api.stop()
        standin.down()


def stop_after_requests(
    provider: str, mode: str, timeout: str | None, target: str
) -> tuple[float, int, int | None]:
    standin = StandIn(free_port())
    getattr(standin, mode)()
    api = Linnet(provider, standin.port, timeout, target)
    for _ in range(10):
        api.chat()
    seconds = api.stop()
    time.sleep(0.5)
    standin.down()
    kept = [n for _, _, n in standin.spans() if n == REQUEST_SPAN]
    return seconds, len(kept), api.proc.returncode


def test_uvicorn_skips_atexit_so_only_the_lifespan_flush_saves_spans(
    provider: str,
) -> None:
    lost = stop_after_requests(provider, "up", None, NO_FLUSH)
    kept = stop_after_requests(
        provider, "up", None, "wrenholt.api.main:app"
    )
    # Uvicorn re-raises SIGTERM, so the process dies by the signal.
    assert lost[2] == kept[2] == -signal.SIGTERM
    assert (lost[1], kept[1]) == (0, 10)


def test_a_two_second_timeout_bounds_shutdown_on_a_hung_receiver(
    provider: str,
) -> None:
    seconds, kept, _ = stop_after_requests(
        provider, "hang", "2", "wrenholt.api.main:app"
    )
    assert kept == 0 and seconds < 8.0
