"""Reproduction bundles: complete, and metadata only."""

from dataclasses import asdict, replace

from wrenholt import __version__
from wrenholt.gateway import RetryPolicy, Route
from wrenholt.labs.fs11_lab import QUESTION, run
from wrenholt.orchestrator.prompts import SUPPORT, Prompt
from wrenholt.repro import config_hash
from wrenholt.telemetry import conventions as c

ROUTE = Route("wrenholt.mock_a", "http://127.0.0.1:8100/v1", "sk")


def test_every_field_is_filled_and_none_is_content() -> None:
    before, _ = run()
    fields = asdict(before.bundle)
    assert len(fields) == 15
    assert all(isinstance(v, str) and v for v in fields.values())
    assert fields["service_version"] == __version__
    assert fields["conventions_commit"] == c.GENAI_COMMIT
    assert fields["prompt_sha256"] == SUPPORT.sha256
    text = before.bundle.to_json()
    assert QUESTION not in text and before.text not in text
    assert SUPPORT.text not in text


def test_config_hash_moves_with_the_config_only() -> None:
    policy = RetryPolicy()
    same = config_hash(ROUTE, "mock-a-fast", policy)
    assert same == config_hash(ROUTE, "mock-a-fast", RetryPolicy())
    fewer = replace(policy, max_attempts=2)
    assert config_hash(ROUTE, "mock-a-fast", fewer) != same
    assert config_hash(ROUTE, "mock-a-large", policy) != same


def test_an_unversioned_prompt_edit_still_shows() -> None:
    edited = Prompt(SUPPORT.name, SUPPORT.version, SUPPORT.text + " ")
    assert edited.sha256 != SUPPORT.sha256
