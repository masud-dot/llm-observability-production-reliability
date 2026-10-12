"""The request record that SLI calculators read.

Later chapters fill these records from telemetry. Chapter 2
builds them directly, so every count in it is reproducible.
"""

from dataclasses import dataclass
from typing import Literal

Journey = Literal["policy_question", "order_status", "refund_request"]
RequestClass = Literal["interactive", "critical_action"]
Outcome = Literal["ok", "server_error", "client_error", "cancelled"]


@dataclass(frozen=True)
class RequestEvent:
    """One customer request as the SLIs see it."""

    journey: Journey
    request_class: RequestClass
    outcome: Outcome
    ttfc_s: float | None = None
    policy_version: str | None = None
    decision_valid: bool | None = None
    grounded: bool | None = None
    escalated: bool = False
