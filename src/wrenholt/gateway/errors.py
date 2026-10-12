"""Provider-neutral errors: a closed set, one retry rule each.

Spans, metrics and the retry loop see only these values, never a
provider's own error classes, so a fallback to another provider
changes no dashboard and no alert.
"""

from enum import StrEnum


class ErrorType(StrEnum):
    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    OVERLOADED = "overloaded"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TIMEOUT = "timeout"
    STREAM_INTERRUPTED = "stream_interrupted"
    INVALID_REQUEST = "invalid_request"
    AUTH = "auth"


# Waiting can fix these. It cannot fix a spent quota, a malformed
# request or a revoked key, and a broken stream may already have
# reached the customer, so Chapter 8 decides those retries.
RETRYABLE: frozenset[ErrorType] = frozenset(
    {
        ErrorType.RATE_LIMITED,
        ErrorType.OVERLOADED,
        ErrorType.PROVIDER_UNAVAILABLE,
        ErrorType.TIMEOUT,
    }
)


class ProviderError(Exception):
    """A failed provider call, already mapped to the closed set."""

    def __init__(
        self,
        error_type: ErrorType,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(error_type.value)
        self.error_type = error_type
        self.status = status
        self.retry_after = (
            retry_after  # seconds, if the provider said
        )

    @property
    def retryable(self) -> bool:
        return self.error_type in RETRYABLE
