"""Provider B serves only its own model; A keeps its two."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = """
from services.mock_llm.app import ChatRequest, Message, respond
from services.mock_llm.faults import NO_FAULTS
for model in ("mock-a-fast", "mock-a-large", "mock-b-standard"):
    req = ChatRequest(model=model, messages=[Message(role="user",
                      content="refund?")])
    print(model, respond(NO_FAULTS, req, 0)[0])
"""


def statuses(provider: str) -> list[str]:
    result = subprocess.run(
        [sys.executable, "-c", CHECK],
        cwd=ROOT,
        env={"MOCK_LLM_PROVIDER": provider, "PATH": ""},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.split()


def test_each_provider_serves_only_its_models() -> None:
    assert statuses("a") == [
        "mock-a-fast", "200", "mock-a-large", "200",
        "mock-b-standard", "404",
    ]  # fmt: skip
    assert statuses("b") == [
        "mock-a-fast", "404", "mock-a-large", "404",
        "mock-b-standard", "200",
    ]  # fmt: skip
