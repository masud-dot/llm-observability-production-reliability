"""The gateway's retry rule: the only one in Linnet.

The backoff matches the provider SDK's defaults (three attempts,
0.5 s doubling to at most 8 s, up to 25 per cent jitter taken
off), so moving retries into the gateway changes their
visibility, not their timing. Chapter 16 adds a retry budget and
replaces max_retry_after with the request's remaining deadline.
"""

from dataclasses import dataclass

from wrenholt.gateway.errors import ProviderError


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0
    # Chapter 2 gives a chat 10 s end to end; a provider asking for
    # a longer wait than this gets no retry.
    max_retry_after: float = 4.0

    def next_delay(
        self, attempt: int, err: ProviderError, jitter: float
    ) -> float | None:
        """Seconds to wait before another attempt; None to stop."""
        if not err.retryable or attempt >= self.max_attempts:
            return None
        if err.retry_after is not None:
            if err.retry_after > self.max_retry_after:
                return None
            return err.retry_after
        backoff = self.base_delay * 2.0 ** (attempt - 1)
        return min(self.max_delay, backoff) * (1 - 0.25 * jitter)
