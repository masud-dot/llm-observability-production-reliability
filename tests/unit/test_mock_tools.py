"""The mock model with tools (Chapter 9, SIMULATED)."""

import json
from typing import Any

from fastapi.testclient import TestClient

from services.mock_llm.app import create_app
from services.mock_llm.tool_loop import with_tool_loop

URL = "/v1/chat/completions"
TOOLS = [{"type": "function", "function": {"name": "lookup_order"}}]
ASK = {"role": "user", "content": "Refund £5.00 on order WG-100006"}


def decide(client: TestClient, messages: list[Any]) -> Any:
    body = {"model": "mock-a-fast", "messages": messages}
    reply = client.post(URL, json={**body, "tools": TOOLS}).json()
    return reply["choices"][0]["message"]["tool_calls"][0]


def answered(call: Any, result: dict[str, object]) -> list[Any]:
    return [
        {"role": "assistant", "content": None, "tool_calls": [call]},
        {
            "role": "tool",
            "tool_call_id": call["id"],
            "content": json.dumps(result),
        },
    ]


def test_lookup_then_refund_then_finish() -> None:
    client = TestClient(create_app())
    asked: list[Any] = [ASK]
    first = decide(client, asked)
    assert first["function"]["name"] == "lookup_order"
    order = {"found": True, "status": "delivered", "total_minor": 900}
    asked += answered(first, order)
    second = decide(client, asked)
    assert second["function"]["name"] == "issue_refund"
    assert json.loads(second["function"]["arguments"]) == {
        "order_id": "WG-100006",
        "amount_minor": 500,
    }
    asked += answered(second, {"refund_id": "RF-000001"})
    assert decide(client, asked)["function"]["name"] == "finish"


def test_fs06_repeats_the_lookup_and_leaves_answers_alone() -> None:
    client = TestClient(with_tool_loop(create_app()))
    asked: list[Any] = [ASK]
    first = decide(client, asked)
    asked += answered(first, {"found": True, "status": "delivered"})
    again = decide(client, asked)
    assert again["function"] == first["function"]
    assert again["id"] != first["id"]  # a new call, the same request
    plain = {"model": "mock-a-fast", "messages": [ASK]}
    reply = client.post(URL, json=plain).json()
    assert reply["choices"][0]["finish_reason"] == "stop"
