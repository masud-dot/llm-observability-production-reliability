"""Linnet's streamed /chat through a real server: the status code
waits for the first chunk, later failures are reported in-band, and
a departure reaches the provider (about fifteen seconds)."""

import pytest

from services.mock_llm.server import running_provider
from services.mock_llm.streaming import STEADY
from services.otlp_standin import StandIn
from services.outage_lab import Linnet, free_port
from wrenholt.labs.fs04_lab import QUESTION, Case, ask, run

INTERRUPTED = (
    "error",
    {"error": "stream_interrupted", "partial": True},
)


@pytest.fixture(scope="module")
def cases() -> list[Case]:
    return run()


def chunks(case: Case) -> int:
    return sum(kind == "chunk" for kind, _ in case.reply.events)


def test_failures_after_200_are_reported_in_band(
    cases: list[Case],
) -> None:
    for case in cases[:2]:  # a cut, then an error event
        assert case.reply.status == 200
        assert chunks(case) == 3
        assert case.reply.events[-1] == INTERRUPTED
        assert (case.error, case.attempts) == (
            "stream_interrupted",
            1,
        )


def test_a_cut_before_the_first_chunk_is_invisible(
    cases: list[Case],
) -> None:
    case = cases[2]
    assert case.reply.events[-1] == ("done", {"finish": "stop"})
    assert chunks(case) == 8
    assert (case.error, case.attempts) == (None, 2)


def test_a_departure_reaches_the_provider(cases: list[Case]) -> None:
    case = cases[3]
    assert case.reply.left and case.cancelled
    assert case.error is None
    assert case.provider.outcome == "client_gone"
    assert case.provider.chunks < case.provider.planned


def test_every_streamed_answer_leaves_a_bundle(
    cases: list[Case],
) -> None:
    assert all(case.bundle for case in cases)


def test_the_vault_keeps_each_outcome_and_the_text_sent(
    cases: list[Case],
) -> None:
    outcomes = [case.kept["outcome"] for case in cases]
    assert outcomes == [
        "interrupted",
        "interrupted",
        "complete",
        "cancelled",
    ]
    for case in cases:
        shown = "".join(
            str(data["text"])
            for kind, data in case.reply.events
            if kind == "chunk"
        )
        # A departing customer may miss a chunk already sent.
        assert case.kept["answer"].startswith(shown)
        if not case.reply.left:
            assert case.kept["answer"] == shown


def test_a_failure_before_the_stream_is_a_503() -> None:
    standin = StandIn(free_port())
    standin.up()
    with running_provider(spend_cap=True, streaming=STEADY) as mock:
        api = Linnet(mock.base_url, standin.port, "2")
        reply = ask(api.port, QUESTION, None)
        api.stop()
    standin.down()
    assert (reply.status, reply.events) == (503, [])
