"""Reproduction bundles (Chapter 6): metadata only, never content.

One bundle per answered request names every version that shaped
the answer. It is recorded off the request path, in its own trace
with a link back to the request, as one structured log record.
"""

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import Link, SpanContext

from wrenholt import __version__
from wrenholt.gateway import RetryPolicy, Route
from wrenholt.orchestrator.prompts import Prompt
from wrenholt.telemetry import conventions as c

LOG = logging.getLogger("wrenholt.repro")
PENDING: set[asyncio.Task[None]] = set()


@dataclass(frozen=True)
class Bundle:
    trace_id: str
    recorded_at: str
    service_version: str
    conventions_commit: str
    prompt_name: str
    prompt_version: str
    prompt_sha256: str
    requested_model: str
    response_model: str
    pinned_model: str
    provider: str
    model_config_sha256: str
    index_version: str
    scenario: str
    seed: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


def config_hash(route: Route, model: str, policy: RetryPolicy) -> str:
    """Everything about the call except the words: who, where,
    which model, and how it retries."""
    shape = {
        "provider": route.provider,
        "server": list(route.server),
        "model": model,
        "retry": asdict(policy),
    }
    text = json.dumps(shape, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def bundle(
    span: SpanContext,
    prompt: Prompt,
    response_model: str,
    route: Route,
    model: str,
    pinned: str,
    policy: RetryPolicy,
    index_version: str = "none",
) -> Bundle:
    return Bundle(
        trace_id=format(span.trace_id, "032x"),
        recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
        service_version=os.environ.get(
            "WRENHOLT_VERSION", __version__
        ),
        conventions_commit=c.GENAI_COMMIT,
        prompt_name=prompt.name,
        prompt_version=prompt.version,
        prompt_sha256=prompt.sha256,
        requested_model=model,
        response_model=response_model,
        pinned_model=pinned or "none",
        provider=route.provider,
        model_config_sha256=config_hash(route, model, policy),
        index_version=index_version,  # Chapter 9
        scenario=os.environ.get("WRENHOLT_SCENARIO", "none"),
        seed=os.environ.get("WRENHOLT_SEED", "none"),
    )


async def record(item: Bundle, request: SpanContext) -> None:
    """Write the bundle in a new trace that links to the request."""
    tracer = trace.get_tracer("wrenholt.repro")
    with tracer.start_as_current_span(
        "record reproduction bundle",
        context=Context(),
        links=[Link(request)],
    ):
        LOG.info(
            "reproduction bundle",
            extra={c.REPRO_BUNDLE: item.to_json()},
        )


def record_later(item: Bundle, request: SpanContext) -> None:
    """Schedule record() without delaying the customer's answer."""
    task = asyncio.get_running_loop().create_task(
        record(item, request)
    )
    PENDING.add(task)
    task.add_done_callback(PENDING.discard)
