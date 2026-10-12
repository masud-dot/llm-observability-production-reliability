"""Fault plans for the mock provider. All results are SIMULATED.

A fault plan decides how the mock provider answers each request
it receives. Chapter 1 needs one fault, rate limiting with a
retry-after header, for FS-01. Later scenarios add more kinds.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FaultPlan:
    """Answer the first N requests with HTTP 429, then serve.

    Requests are counted in arrival order at the provider, so
    every attempt counts, whichever client sent it.
    """

    rate_limited_requests: int = 0
    retry_after_s: int = 1

    def rate_limits(self, arrival: int) -> bool:
        """True if the request with this arrival index gets 429."""
        return arrival < self.rate_limited_requests


NO_FAULTS = FaultPlan()

# FS-01 hidden retry storm: two 429 responses, each asking the
# client to wait one second, then normal service.
FS01_HIDDEN_RETRY_STORM = FaultPlan(
    rate_limited_requests=2,
    retry_after_s=1,
)

PLANS = {"none": NO_FAULTS, "fs01": FS01_HIDDEN_RETRY_STORM}
