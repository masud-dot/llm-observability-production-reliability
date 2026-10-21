"""The error map: one closed set, one retry rule per value."""

import pytest

from wrenholt.gateway.errors import (
    RETRYABLE,
    ErrorType,
    ProviderError,
)
from wrenholt.gateway.openai_compat import classify, retry_after
from wrenholt.gateway.policy import RetryPolicy

E = ErrorType
Q = ErrorType.QUOTA_EXHAUSTED
CASES = [
    # status, error.code, error.type -> neutral error.type
    (429, None, None, E.RATE_LIMITED),
    (429, "slow_down", "rate_limit_error", E.RATE_LIMITED),
    (429, "project_spend_limit_exceeded", "insufficient_quota", Q),
    (429, "organization_spend_limit_exceeded", None, Q),
    (429, "organization_usage_limit_exceeded", None, Q),
    (429, "credit_balance_exhausted", None, Q),
    (429, None, "insufficient_quota", Q),
    (402, None, None, Q),
    (401, None, None, E.AUTH),
    (403, None, None, E.AUTH),
    (400, None, "invalid_request_error", E.INVALID_REQUEST),
    (404, None, None, E.INVALID_REQUEST),
    (422, None, None, E.INVALID_REQUEST),
    (408, None, None, E.TIMEOUT),
    (504, None, None, E.TIMEOUT),
    (503, "server_is_overloaded", "service_unavailable_error",
     E.OVERLOADED),
    (529, None, "overloaded_error", E.OVERLOADED),
    (500, None, None, E.PROVIDER_UNAVAILABLE),
    (502, None, None, E.PROVIDER_UNAVAILABLE),
]  # fmt: skip


@pytest.mark.parametrize(
    ("status", "code", "kind", "expected"), CASES
)
def test_classify(
    status: int, code: str | None, kind: str | None, expected: E
) -> None:
    assert classify(status, code, kind) is expected


def test_only_waitable_errors_are_retryable() -> None:
    assert RETRYABLE == {
        E.RATE_LIMITED,
        E.OVERLOADED,
        E.PROVIDER_UNAVAILABLE,
        E.TIMEOUT,
    }


@pytest.mark.parametrize(
    ("headers", "seconds"),
    [
        ({"retry-after": "1"}, 1.0),
        ({"retry-after-ms": "1500", "retry-after": "9"}, 1.5),
        ({"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}, None),
        ({}, None),
    ],
)
def test_retry_after(
    headers: dict[str, str], seconds: float | None
) -> None:
    assert retry_after(headers) == seconds


def test_policy_matches_the_sdk_backoff_and_stops_where_it_must() -> (
    None
):
    policy = RetryPolicy()
    limited = ProviderError(E.RATE_LIMITED, 429)
    # No retry-after: 0.5 s, then 1.0 s, less up to 25 % jitter.
    assert policy.next_delay(1, limited, jitter=0.0) == 0.5
    assert policy.next_delay(2, limited, jitter=1.0) == 0.75
    assert policy.next_delay(3, limited, jitter=0.0) is None
    asked = ProviderError(E.RATE_LIMITED, 429, retry_after=1.0)
    assert policy.next_delay(1, asked, jitter=0.5) == 1.0
    too_long = ProviderError(E.RATE_LIMITED, 429, retry_after=30.0)
    assert policy.next_delay(1, too_long, jitter=0.0) is None
    quota = ProviderError(E.QUOTA_EXHAUSTED, 429)
    assert policy.next_delay(1, quota, jitter=0.0) is None
