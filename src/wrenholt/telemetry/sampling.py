"""Which traces the production-like Collector keeps (Chapter 10).

Metrics count every request; traces reach Tempo only when a
tail-sampling policy keeps them. Every panel on the gateway
dashboard shows a signal someone will want traces for, so each
names the policy that keeps the traces behind it, or the baseline
when the signal fires on so many requests during an incident that
one in ten is plenty. A test compares this map with
deploy/compose/otelcol/config.production.yaml and the dashboard,
so a new panel cannot ship without saying which traces back it.
"""

from dataclasses import dataclass
from typing import Final

from wrenholt.orchestrator.guard import REPEATED, STEP_LIMIT
from wrenholt.telemetry import conventions as c

BASELINE: Final = "baseline"
# The degraded modes of Chapter 17's ladder, and refusals.
DEGRADED: Final = (
    "fallback_model",
    "cached",
    "citation_only",
    "handoff",
    "refused",
)
BASELINE_PERCENT: Final = 10


@dataclass(frozen=True)
class Policy:
    name: str
    type: str  # a tail_sampling policy type
    key: str = ""  # the span attribute it reads, if any
    values: tuple[str, ...] = ()


@dataclass(frozen=True)
class Keep:
    panel: str  # a panel title on the gateway dashboard
    policy: str  # the policy that keeps the traces behind it


POLICIES: Final = (
    # A failed attempt is an error span (Chapter 4), so the errors
    # policy also keeps every request that needed a retry.
    Policy("errors", "status_code"),
    Policy(
        "slow-first-chunk",
        "ottl_condition",
        c.RESPONSE_TIME_TO_FIRST_CHUNK,
    ),
    Policy("slow", "latency"),
    Policy(
        "loop-stopped",
        "string_attribute",
        c.AGENT_STOP,
        (REPEATED, STEP_LIMIT),
    ),
    Policy("replayed-write", "boolean_attribute", c.TOOL_REPLAYED),
    Policy("model-mismatch", "boolean_attribute", c.MODEL_MISMATCH),
    Policy(BASELINE, "probabilistic"),
    # Chapter 17: every answer made other than in full.
    Policy("degraded", "string_attribute", c.DEGRADED_MODE, DEGRADED),
)

KEEP: Final = (
    Keep("Attempts by error type", "errors"),
    Keep("Request duration p95 by provider", "slow"),
    Keep("Requests ended by a spent quota (1 h)", "errors"),
    Keep("Requests that needed a retry", "errors"),
    Keep("Responses from an unpinned model (1 h)", "model-mismatch"),
    Keep("Time to first chunk p95 by provider", "slow-first-chunk"),
    Keep(
        "First chunk within 2.5 s (ttfc SLI, 1 h)", "slow-first-chunk"
    ),
    # During FS-08 every retrieval is empty: the baseline is plenty.
    Keep("Retrievals that found nothing, by index", BASELINE),
    Keep("Tool calls per invocation p95", "loop-stopped"),
    Keep("Agent invocations by stop reason (1 h)", "loop-stopped"),
    Keep("Refunds answered by a replay", "replayed-write"),
)
