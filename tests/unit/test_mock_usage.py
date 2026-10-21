"""What the mock provider bills and reports (Chapter 11).

SIMULATED: words stand in for tokens."""

import json
from typing import Any

import httpx
from fastapi.testclient import TestClient

from services.mock_llm.app import (
    PADDING,
    PREFIX_CACHE,
    count_tokens,
    create_app,
)
from services.mock_llm.server import running_provider
from services.mock_llm.streaming import Schedule

SYSTEM = "You are Linnet. Answer briefly."
QUESTION = "When will my refund arrive?"
ANSWER = "Refunds reach your card within five working days."
TOOLS = [{"type": "function", "function": {"name": "finish"}}]


def ask(
    client: TestClient, system: str = SYSTEM, **extra: object
) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": QUESTION},
    ]
    body = {"model": "mock-a-fast", "messages": messages, **extra}
    reply = client.post("/v1/chat/completions", json=body)
    return dict(reply.json())


def test_the_cap_cuts_the_answer_and_says_so() -> None:
    client = TestClient(create_app())
    reply = ask(client, max_completion_tokens=3)
    choice = reply["choices"][0]
    assert choice["message"]["content"] == "Refunds reach your"
    assert choice["finish_reason"] == "length"
    assert reply["usage"]["completion_tokens"] == 3
    assert ask(client, max_tokens=3)["choices"] == reply["choices"]


def test_asked_to_be_thorough_it_pads() -> None:
    reply = ask(TestClient(create_app()), "Answer thoroughly.")
    text = reply["choices"][0]["message"]["content"]
    assert text == " ".join([ANSWER, *[PADDING] * 4])
    assert reply["usage"]["completion_tokens"] == 8 + 4 * 20


def test_the_system_prompt_is_cached_after_its_first_use() -> None:
    PREFIX_CACHE.clear()
    client = TestClient(create_app())
    first, second = ask(client), ask(client)
    assert first["usage"]["prompt_tokens_details"] == {
        "cached_tokens": 0
    }
    cached = second["usage"]["prompt_tokens_details"]["cached_tokens"]
    assert cached == count_tokens(SYSTEM) == 5
    assert second["usage"]["prompt_tokens"] == 5 + 5  # all input


def test_offered_tools_are_input_tokens() -> None:
    client = TestClient(create_app())
    plain = ask(client)["usage"]["prompt_tokens"]
    offered = ask(client, tools=TOOLS)["usage"]["prompt_tokens"]
    assert offered - plain == count_tokens(json.dumps(TOOLS)) == 5


def events(base_url: str, usage: bool) -> list[dict[str, Any]]:
    body: dict[str, object] = {
        "model": "mock-a-fast",
        "stream": True,
        "messages": [{"role": "user", "content": QUESTION}],
    }
    if usage:
        body["stream_options"] = {"include_usage": True}
    with httpx.stream(
        "POST", f"{base_url}/chat/completions", json=body
    ) as reply:
        lines = [line for line in reply.iter_lines() if line]
    return [
        json.loads(line.removeprefix("data: "))
        for line in lines
        if line != "data: [DONE]"
    ]


def test_a_stream_sends_usage_last_only_when_asked() -> None:
    fast = Schedule(first_s=0.01, gap_s=0.01)
    with running_provider(streaming=fast) as mock:
        plain = events(mock.base_url, usage=False)
        asked = events(mock.base_url, usage=True)
    assert all("usage" not in e for e in plain)
    assert [e["choices"] for e in asked[:-1]] == [
        e["choices"] for e in plain
    ]
    assert asked[-1]["choices"] == []
    assert asked[-1]["usage"]["completion_tokens"] == 8
