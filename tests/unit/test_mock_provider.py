"""Mock provider: deterministic answers and the FS-01 fault plan."""

from fastapi.testclient import TestClient

from services.mock_llm.app import ProviderLog, create_app, pick_answer
from services.mock_llm.faults import (
    FS01_HIDDEN_RETRY_STORM,
    FaultPlan,
)

BODY = {
    "model": "mock-a-fast",
    "messages": [{"role": "user", "content": "Where is my refund?"}],
}


def test_answers_are_chosen_by_keyword() -> None:
    assert pick_answer("Where is my REFUND?").startswith("Refunds")
    assert pick_answer("hello") == (
        "I can help with orders, returns and refunds."
    )


def test_fault_plan_counts_arrivals() -> None:
    plan = FaultPlan(rate_limited_requests=2)
    assert [plan.rate_limits(i) for i in range(4)] == [
        True,
        True,
        False,
        False,
    ]


def test_fs01_plan_rate_limits_twice_then_serves() -> None:
    log = ProviderLog()
    client = TestClient(create_app(FS01_HIDDEN_RETRY_STORM, log))
    url = "/v1/chat/completions"
    replies = [client.post(url, json=BODY) for _ in range(3)]
    assert [r.status_code for r in replies] == [429, 429, 200]
    assert replies[0].headers["retry-after"] == "1"
    assert replies[2].json()["model"] == "mock-a-fast-2026-09"
    assert [item.status for item in log.items()] == [429, 429, 200]


def test_unknown_model_is_rejected() -> None:
    client = TestClient(create_app())
    body = {**BODY, "model": "no-such-model"}
    reply = client.post("/v1/chat/completions", json=body)
    assert reply.status_code == 404
