"""Retries at two layers multiply provider requests (Section 1.3)."""

import openai
import pytest

from services.mock_llm.faults import FaultPlan
from services.mock_llm.server import running_provider
from wrenholt.orchestrator.baseline import answer, make_client


def test_two_retry_layers_multiply_provider_requests() -> None:
    always = FaultPlan(rate_limited_requests=10**6, retry_after_s=1)
    with running_provider(always) as provider:
        client = make_client(provider.base_url, "sk-mock")
        for _ in range(2):  # an application-level retry on top
            with pytest.raises(openai.RateLimitError):
                answer(client, "mock-a-fast", "Where is my refund?")
        received = provider.log.items()
    # 2 application calls x 3 SDK attempts = 6 provider requests.
    assert [item.status for item in received] == [429] * 6
    assert [item.retry_count for item in received] == [
        "0",
        "1",
        "2",
        "0",
        "1",
        "2",
    ]
