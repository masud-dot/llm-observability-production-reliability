"""Baseline smoke: Linnet answers through the mock provider."""

from fastapi.testclient import TestClient

from services.mock_llm.server import running_provider
from wrenholt.api.app import Settings, create_app


def test_baseline_answers_through_the_mock_provider() -> None:
    with running_provider() as provider:
        settings = Settings(provider_url=provider.base_url)
        with TestClient(create_app(settings)) as client:
            reply = client.post(
                "/chat", json={"message": "How do refunds work?"}
            )
        received = provider.log.items()
    assert reply.status_code == 200
    assert reply.json()["answer"].startswith("Refunds")
    assert [item.status for item in received] == [200]
    assert [item.retry_count for item in received] == ["0"]
