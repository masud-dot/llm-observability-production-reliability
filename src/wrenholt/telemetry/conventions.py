"""Every telemetry name Wrenholt's own code emits (Option B).

GenAI names follow open-telemetry/semantic-conventions-genai at
bcc7f9c (29 Sep 2026), where every GenAI signal is Development.
wrenholt.* names are book-defined. Durations are in seconds.
REGISTRY, at the end, records where every name comes from; the
drift tests in tests/drift check it against a snapshot of the
pinned commit (Chapter 5).
"""

from dataclasses import dataclass
from typing import Final

# GenAI conventions (Development)
OPERATION_NAME: Final = "gen_ai.operation.name"
PROVIDER_NAME: Final = "gen_ai.provider.name"
REQUEST_MODEL: Final = "gen_ai.request.model"
RESPONSE_MODEL: Final = "gen_ai.response.model"
RESPONSE_ID: Final = "gen_ai.response.id"
FINISH_REASONS: Final = "gen_ai.response.finish_reasons"
INPUT_TOKENS: Final = "gen_ai.usage.input_tokens"
OUTPUT_TOKENS: Final = "gen_ai.usage.output_tokens"
OPERATION_DURATION: Final = "gen_ai.client.operation.duration"
PROMPT_NAME: Final = "gen_ai.prompt.name"
TIME_TO_FIRST_CHUNK: Final = (
    "gen_ai.client.operation.time_to_first_chunk"
)
TIME_PER_OUTPUT_CHUNK: Final = (
    "gen_ai.client.operation.time_per_output_chunk"
)
RESPONSE_TIME_TO_FIRST_CHUNK: Final = (
    "gen_ai.response.time_to_first_chunk"  # on the request span
)
PROMPT_VERSION: Final = "gen_ai.prompt.version"
CHAT: Final = "chat"
# Chapter 9: retrieval, tools and agents. Operation names first,
# then attributes and metrics.
RETRIEVAL: Final = "retrieval"
EMBEDDINGS: Final = "embeddings"
EXECUTE_TOOL: Final = "execute_tool"
INVOKE_AGENT: Final = "invoke_agent"
DATA_SOURCE_ID: Final = "gen_ai.data_source.id"
RETRIEVAL_TOP_K: Final = "gen_ai.retrieval.top_k"
RETRIEVAL_DOCUMENTS: Final = "gen_ai.retrieval.documents"  # opt-in
EMBEDDING_DIMENSIONS: Final = "gen_ai.embeddings.dimension.count"
AGENT_NAME: Final = "gen_ai.agent.name"
AGENT_DESCRIPTION: Final = "gen_ai.agent.description"
TOOL_NAME: Final = "gen_ai.tool.name"
TOOL_TYPE: Final = "gen_ai.tool.type"
TOOL_CALL_ID: Final = "gen_ai.tool.call.id"
AGENT_DURATION: Final = "gen_ai.invoke_agent.duration"
AGENT_INFERENCE_CALLS: Final = "gen_ai.invoke_agent.inference_calls"
AGENT_TOOL_CALLS: Final = "gen_ai.invoke_agent.tool_calls"
TOOL_DURATION: Final = "gen_ai.execute_tool.duration"
# Bucket boundaries the conventions advise for the duration.
DURATION_BUCKETS: Final = (
    0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64,
    1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92,
)  # fmt: skip
# Chapter 8. Both streaming histograms SHOULD use the duration's
# boundaries at the pinned commit. Time to first chunk adds the
# ttfc SLI thresholds from Chapter 2, so good events can be counted
# exactly from one bucket; a test keeps the two in step.
CHUNK_BUCKETS: Final = DURATION_BUCKETS
SLI_THRESHOLDS: Final = (2.5, 4.0)
TTFC_BUCKETS: Final = tuple(sorted({*CHUNK_BUCKETS, *SLI_THRESHOLDS}))
# Chapter 9: the boundaries the conventions advise for the agent's
# duration and per-invocation counts; tool durations use the
# operation duration's.
AGENT_BUCKETS: Final = (
    0.1, 0.2, 0.4, 0.8, 1.6, 3.2, 6.4,
    12.8, 25.6, 51.2, 102.4, 204.8, 409.6,
)  # fmt: skip
CALL_BUCKETS: Final = (1, 2, 4, 8, 16, 32, 64, 128)

# General conventions (Stable)
ERROR_TYPE: Final = "error.type"
SERVER_ADDRESS: Final = "server.address"
SERVER_PORT: Final = "server.port"
HTTP_STATUS: Final = "http.response.status_code"

# Resource attributes (Stable), set once per process (Chapter 6)
SERVICE_NAMESPACE: Final = "service.namespace"
SERVICE_VERSION: Final = "service.version"
DEPLOYMENT_ENVIRONMENT: Final = "deployment.environment.name"

# Book-defined
ATTEMPT_COUNT: Final = "wrenholt.gateway.attempt_count"
ATTEMPTS: Final = "wrenholt.gateway.attempts"  # counter
ATTEMPT_NUMBER: Final = "wrenholt.attempt.number"
ATTEMPT_DELAY: Final = "wrenholt.attempt.delay"
ATTEMPT_RETRY_AFTER: Final = "wrenholt.attempt.retry_after"
ATTEMPT_RETRYABLE: Final = "wrenholt.attempt.retryable"
MODEL_MISMATCH: Final = "wrenholt.gateway.model_mismatch"
MODEL_MISMATCHES: Final = (
    "wrenholt.gateway.model_mismatches"  # counter
)
STREAM_CHUNKS: Final = "wrenholt.stream.chunks"
STREAM_CANCELLED: Final = "wrenholt.stream.cancelled"
# A log attribute, not on spans: the reproduction bundle (Chapter 6).
REPRO_BUNDLE: Final = "wrenholt.repro.bundle"
# Chapter 7: the vault reference on the API's server span, and the
# redaction counter with its two attributes.
CONTENT_REF: Final = "wrenholt.content.ref"
REDACTIONS: Final = "wrenholt.privacy.redactions"  # counter
PRIVACY_KIND: Final = "wrenholt.privacy.kind"
PRIVACY_WHERE: Final = "wrenholt.privacy.where"
# Chapter 9: which index answered, what the context kept, why the
# loop ended, and what a tool call did, never its arguments.
INDEX_VERSION: Final = "wrenholt.index.version"
INDEX_EMBEDDER: Final = "wrenholt.index.embedder"
RETURNED: Final = "wrenholt.retrieval.returned"  # histogram
CONTEXT_BUDGET: Final = "wrenholt.context.budget"
CONTEXT_TOKENS: Final = "wrenholt.context.tokens"
CONTEXT_DROPPED: Final = "wrenholt.context.dropped"
AGENT_STOP: Final = "wrenholt.agent.stop_reason"
TOOL_FINGERPRINT: Final = "wrenholt.tool.call.fingerprint"
TOOL_REPLAYED: Final = "wrenholt.tool.replayed"
RETURNED_BUCKETS: Final = (0, 1, 2, 3)  # top_k is 3
# Chapter 11: tokens and what they cost. The usage counters and the
# per-call histogram come from the token-metric redesign (GenAI,
# Development); cost, tenant and limit names are the book's. Linnet
# sends and receives text only, so every token it counts is text.
TOKEN_MODALITY: Final = "gen_ai.token.modality"
TEXT: Final = "text"
REQUEST_MAX_TOKENS: Final = "gen_ai.request.max_tokens"
CACHE_READ_TOKENS: Final = "gen_ai.usage.cache_read.input_tokens"
USAGE_INPUT: Final = "gen_ai.client.inference.usage.input_tokens"
USAGE_OUTPUT: Final = "gen_ai.client.inference.usage.output_tokens"
USAGE_CACHE_READ: Final = (
    "gen_ai.client.inference.usage.cache_read.input_tokens"
)
OUTPUT_PER_CALL: Final = (
    "gen_ai.client.inference.operation.output_tokens"
)
TENANT: Final = "wrenholt.tenant"
COST: Final = "wrenholt.gateway.cost"  # counter, US dollars
CALL_COST: Final = "wrenholt.cost"  # one call's, on its span
ANSWER_COST: Final = "wrenholt.answer.cost"  # on the agent span
PRICE_TABLE: Final = "wrenholt.price_table"  # the table's version
LIMITED: Final = "wrenholt.gateway.limited"  # calls refused
SPEND_LIMIT: Final = "wrenholt.gateway.spend_limit"  # gauge
CONSUMPTION_LIMIT: Final = "consumption_limit"  # error.type, spans
# The specification's advice for both per-call token histograms.
TOKEN_BUCKETS: Final = (
    1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576,
    4194304, 16777216, 67108864,
)  # fmt: skip
# Chapter 12: what the API judges for the SLIs, the customer's time
# to first chunk and the input guardrail, all the book's names.
# Objectives and thresholds live in src/wrenholt/slo/objectives.yaml.
SLO_EVENTS: Final = "wrenholt.slo.events"  # counter, good or bad
SLO_SLI: Final = "wrenholt.slo.sli"
SLO_GOOD: Final = "wrenholt.slo.good"
EVENT_SLIS: Final = (
    "availability",
    "not_refused",
    "policy_freshness",
    "answer_cost",
    "resolution",
)
ANSWER_FIRST_CHUNK: Final = "wrenholt.answer.time_to_first_chunk"
REQUEST_CLASS: Final = "wrenholt.request_class"
REQUEST_CLASSES: Final = ("interactive", "critical_action")
# The customer's thresholds, and a few boundaries to show the shape.
ANSWER_BUCKETS: Final = (0.5, 1.0, *SLI_THRESHOLDS, 6.0, 10.0)
GUARDRAIL: Final = "wrenholt.guardrail"  # its tracer and span
GUARDRAIL_VERSION: Final = "wrenholt.guardrail.version"
GUARDRAIL_RULE: Final = "wrenholt.guardrail.rule"  # when it blocks
# Chapter 13: evaluation results as telemetry. The event and its
# attributes are the GenAI conventions' (Development); the counter
# and the evaluator's version are the book's.
EVALUATION_RESULT: Final = "gen_ai.evaluation.result"  # an event
EVALUATION_NAME: Final = "gen_ai.evaluation.name"
EVALUATION_SCORE: Final = "gen_ai.evaluation.score.value"
EVALUATION_LABEL: Final = "gen_ai.evaluation.score.label"
EVALUATOR_VERSION: Final = "wrenholt.evaluator.version"
EVALUATION_RESULTS: Final = "wrenholt.evaluation.results"  # counter
# Chapter 16: the gateway's protective decisions. Spans only: the
# instance's series budget has no room for another metric.
RETRY_DECISION: Final = "wrenholt.retry.decision"
RETRY_WAIT: Final = "wrenholt.retry.wait"  # seconds
DEADLINE_LEFT: Final = "wrenholt.deadline.remaining"  # seconds
BREAKER_STATE: Final = "wrenholt.breaker.state"
LIMIT_IN_FLIGHT: Final = "wrenholt.limit.in_flight"
# Span events that carry them (book names). Not in REGISTRY, whose
# events are checked against the pinned conventions.
RETRY_EVENT: Final = "wrenholt.retry"
BREAKER_EVENT: Final = "wrenholt.breaker"


# The pinned specification the GenAI names come from.
GENAI_COMMIT: Final = "bcc7f9c2856fa7f4feb753f54d4ebba9455cc3dc"

# Opt-in content attributes. Wrenholt never emits them: content
# goes to the vault, by reference (Chapter 7).
CONTENT: Final = (
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.system_instructions",
    "gen_ai.tool.definitions",
    # Chapter 9: what was searched for and what tools received and
    # returned. Only the facts Linnet builds reach the model again.
    "gen_ai.retrieval.query.text",
    "gen_ai.tool.call.arguments",
    "gen_ai.tool.call.result",
)


@dataclass(frozen=True)
class Name:
    """One emitted name and where it comes from."""

    name: str
    kind: str  # "attribute" or "metric"
    source: str  # "genai" (pinned), "core" (Stable) or "book"
    instrument: str = ""  # metrics only
    unit: str = ""  # metrics only


REGISTRY: Final = (
    Name(OPERATION_NAME, "attribute", "genai"),
    Name(PROVIDER_NAME, "attribute", "genai"),
    Name(REQUEST_MODEL, "attribute", "genai"),
    Name(RESPONSE_MODEL, "attribute", "genai"),
    Name(RESPONSE_ID, "attribute", "genai"),
    Name(FINISH_REASONS, "attribute", "genai"),
    Name(INPUT_TOKENS, "attribute", "genai"),
    Name(OUTPUT_TOKENS, "attribute", "genai"),
    Name(OPERATION_DURATION, "metric", "genai", "histogram", "s"),
    Name(ERROR_TYPE, "attribute", "core"),
    Name(SERVER_ADDRESS, "attribute", "core"),
    Name(SERVER_PORT, "attribute", "core"),
    Name(HTTP_STATUS, "attribute", "core"),
    Name(ATTEMPT_COUNT, "attribute", "book"),
    Name(ATTEMPTS, "metric", "book", "counter", "{attempt}"),
    Name(ATTEMPT_NUMBER, "attribute", "book"),
    Name(ATTEMPT_DELAY, "attribute", "book"),
    Name(ATTEMPT_RETRY_AFTER, "attribute", "book"),
    Name(ATTEMPT_RETRYABLE, "attribute", "book"),
    # Chapter 6: prompt metadata and the model pin (FS-11).
    Name(PROMPT_NAME, "attribute", "genai"),
    Name(PROMPT_VERSION, "attribute", "genai"),
    Name(MODEL_MISMATCH, "attribute", "book"),
    Name(MODEL_MISMATCHES, "metric", "book", "counter", "{response}"),
    # Chapter 7: redaction before export.
    Name(REDACTIONS, "metric", "book", "counter", "{redaction}"),
    # Chapter 8: streaming.
    Name(TIME_TO_FIRST_CHUNK, "metric", "genai", "histogram", "s"),
    Name(TIME_PER_OUTPUT_CHUNK, "metric", "genai", "histogram", "s"),
    Name(STREAM_CHUNKS, "attribute", "book"),
    Name(STREAM_CANCELLED, "attribute", "book"),
    Name(RESPONSE_TIME_TO_FIRST_CHUNK, "attribute", "genai"),
    # Chapter 9: retrieval, tools and the agent loop.
    Name(DATA_SOURCE_ID, "attribute", "genai"),
    Name(RETRIEVAL_TOP_K, "attribute", "genai"),
    Name(RETRIEVAL_DOCUMENTS, "attribute", "genai"),
    Name(EMBEDDING_DIMENSIONS, "attribute", "genai"),
    Name(AGENT_NAME, "attribute", "genai"),
    Name(AGENT_DESCRIPTION, "attribute", "genai"),
    Name(TOOL_NAME, "attribute", "genai"),
    Name(TOOL_TYPE, "attribute", "genai"),
    Name(TOOL_CALL_ID, "attribute", "genai"),
    Name(AGENT_DURATION, "metric", "genai", "histogram", "s"),
    Name(
        AGENT_INFERENCE_CALLS,
        "metric",
        "genai",
        "histogram",
        "{inference_call}",
    ),
    Name(
        AGENT_TOOL_CALLS,
        "metric",
        "genai",
        "histogram",
        "{tool_call}",
    ),
    Name(TOOL_DURATION, "metric", "genai", "histogram", "s"),
    Name(INDEX_VERSION, "attribute", "book"),
    Name(INDEX_EMBEDDER, "attribute", "book"),
    Name(RETURNED, "metric", "book", "histogram", "{document}"),
    Name(CONTEXT_BUDGET, "attribute", "book"),
    Name(CONTEXT_TOKENS, "attribute", "book"),
    Name(CONTEXT_DROPPED, "attribute", "book"),
    Name(AGENT_STOP, "attribute", "book"),
    Name(TOOL_FINGERPRINT, "attribute", "book"),
    Name(TOOL_REPLAYED, "attribute", "book"),
    # Chapter 11: tokens, cost and the consumption limit.
    Name(TOKEN_MODALITY, "attribute", "genai"),
    Name(REQUEST_MAX_TOKENS, "attribute", "genai"),
    Name(CACHE_READ_TOKENS, "attribute", "genai"),
    Name(USAGE_INPUT, "metric", "genai", "counter", "{token}"),
    Name(USAGE_OUTPUT, "metric", "genai", "counter", "{token}"),
    Name(USAGE_CACHE_READ, "metric", "genai", "counter", "{token}"),
    Name(OUTPUT_PER_CALL, "metric", "genai", "histogram", "{token}"),
    Name(TENANT, "attribute", "book"),
    Name(CALL_COST, "attribute", "book"),
    Name(ANSWER_COST, "attribute", "book"),
    Name(PRICE_TABLE, "attribute", "book"),
    Name(COST, "metric", "book", "counter", "{USD}"),
    Name(LIMITED, "metric", "book", "counter", "{call}"),
    Name(SPEND_LIMIT, "metric", "book", "gauge", "{USD}"),
    # Chapter 12: SLI events, the first chunk and the guardrail.
    Name(SLO_EVENTS, "metric", "book", "counter", "{event}"),
    Name(SLO_SLI, "attribute", "book"),
    Name(SLO_GOOD, "attribute", "book"),
    Name(ANSWER_FIRST_CHUNK, "metric", "book", "histogram", "s"),
    Name(REQUEST_CLASS, "attribute", "book"),
    Name(GUARDRAIL_VERSION, "attribute", "book"),
    Name(GUARDRAIL_RULE, "attribute", "book"),
    # Chapter 13: evaluation results.
    Name(EVALUATION_NAME, "attribute", "genai"),
    Name(EVALUATION_SCORE, "attribute", "genai"),
    Name(EVALUATION_LABEL, "attribute", "genai"),
    Name(EVALUATOR_VERSION, "attribute", "book"),
    # Chapter 16: protective decisions, on spans.
    Name(RETRY_DECISION, "attribute", "book"),
    Name(RETRY_WAIT, "attribute", "book"),
    Name(DEADLINE_LEFT, "attribute", "book"),
    Name(BREAKER_STATE, "attribute", "book"),
    Name(LIMIT_IN_FLIGHT, "attribute", "book"),
    Name(EVALUATION_RESULTS, "metric", "book", "counter", "{result}"),
)
# Events, checked against the pinned conventions' events.
EVENTS: Final = (Name(EVALUATION_RESULT, "event", "genai"),)


# Chapter 10: the cardinality budget. A metric may carry only the
# attributes its budget lists, and their values may combine in at
# most `combinations` ways in one service instance. Identifiers never
# appear: they belong on spans. The guard in budget.py enforces the
# attribute lists at record time; the drift tests check the code
# against them before it ships.
@dataclass(frozen=True)
class Budget:
    metric: str
    attributes: tuple[str, ...]
    combinations: int
    buckets: tuple[float, ...] = ()  # histograms only

    @property
    def series(self) -> int:
        """Series Prometheus stores: one per combination for a
        counter; for a histogram, a bucket per boundary, the +Inf
        bucket, the sum and the count."""
        per = len(self.buckets) + 3 if self.buckets else 1
        return self.combinations * per


OTHER: Final = "_OTHER"  # what a value outside a closed set becomes
# Tool names come from the model's output (Chapter 9). On metrics,
# any name but those Linnet offers becomes OTHER.
TOOLS: Final = ("lookup_order", "issue_refund", "finish")
CLOSED: Final = {TOOL_NAME: TOOLS}
ROUTE: Final = (
    PROVIDER_NAME,
    REQUEST_MODEL,
    SERVER_ADDRESS,
    SERVER_PORT,
)
OUTCOME: Final = (RESPONSE_MODEL, ERROR_TYPE)
SERIES_BUDGET: Final = 2000  # per service instance

BUDGET: Final = (
    # chat: 3 routes x (2 response models, 8 errors, or 2 models with
    # stream_interrupted); retrieval 1; embeddings 2 embedders
    Budget(
        OPERATION_DURATION,
        (OPERATION_NAME, *ROUTE, *OUTCOME),
        39,
        DURATION_BUCKETS,
    ),
    # 3 routes x 2 response models
    Budget(
        TIME_TO_FIRST_CHUNK,
        (OPERATION_NAME, *ROUTE, RESPONSE_MODEL),
        6,
        TTFC_BUCKETS,
    ),
    Budget(
        TIME_PER_OUTPUT_CHUNK,
        (OPERATION_NAME, *ROUTE, RESPONSE_MODEL),
        6,
        CHUNK_BUCKETS,
    ),
    # 3 routes x (success or 8 errors)
    Budget(ATTEMPTS, (PROVIDER_NAME, REQUEST_MODEL, ERROR_TYPE), 27),
    # 3 routes x 1 substitute model
    Budget(
        MODEL_MISMATCHES,
        (PROVIDER_NAME, REQUEST_MODEL, RESPONSE_MODEL),
        3,
    ),
    # 5 kinds x 2 places (span, log)
    Budget(REDACTIONS, (PRIVACY_KIND, PRIVACY_WHERE), 10),
    # 4 stop reasons x (success or 8 errors)
    Budget(
        AGENT_DURATION,
        (AGENT_NAME, AGENT_STOP, ERROR_TYPE),
        36,
        AGENT_BUCKETS,
    ),
    Budget(AGENT_INFERENCE_CALLS, (AGENT_NAME,), 1, CALL_BUCKETS),
    Budget(AGENT_TOOL_CALLS, (AGENT_NAME,), 1, CALL_BUCKETS),
    # 4 names (3 tools and OTHER) x (success or 4 tool errors)
    Budget(
        TOOL_DURATION,
        (TOOL_NAME, TOOL_TYPE, AGENT_NAME, ERROR_TYPE),
        20,
        DURATION_BUCKETS,
    ),
    # 1 data source x 2 index builds (old and new during a swap)
    Budget(
        RETURNED,
        (DATA_SOURCE_ID, INDEX_VERSION),
        2,
        RETURNED_BUCKETS,
    ),
    # Chapter 11. Tokens: 3 routes x 2 response models, text only.
    Budget(
        USAGE_INPUT,
        (OPERATION_NAME, *ROUTE, RESPONSE_MODEL, TOKEN_MODALITY),
        6,
    ),
    Budget(
        USAGE_OUTPUT,
        (OPERATION_NAME, *ROUTE, RESPONSE_MODEL, TOKEN_MODALITY),
        6,
    ),
    Budget(
        USAGE_CACHE_READ,
        (OPERATION_NAME, *ROUTE, RESPONSE_MODEL, TOKEN_MODALITY),
        6,
    ),
    # 3 routes. The response model, only Recommended here, would
    # double the histogram's 51 series.
    Budget(
        OUTPUT_PER_CALL, (OPERATION_NAME, *ROUTE), 3, TOKEN_BUCKETS
    ),
    # 1 tenant x 3 routes x 2 response models x 2 prompt versions
    # (the one in force and its successor while it rolls out)
    Budget(
        COST,
        (
            TENANT,
            PROVIDER_NAME,
            REQUEST_MODEL,
            RESPONSE_MODEL,
            PROMPT_VERSION,
        ),
        12,
    ),
    # the tenant, or _OTHER for a name without a limit
    Budget(LIMITED, (TENANT,), 2),
    Budget(SPEND_LIMIT, (TENANT,), 1),
    # Chapter 12: 5 SLIs the API judges x good or bad, every one
    # recorded at zero when the API starts
    Budget(SLO_EVENTS, (SLO_SLI, SLO_GOOD), 10),
    # 2 request classes
    Budget(ANSWER_FIRST_CHUNK, (REQUEST_CLASS,), 2, ANSWER_BUCKETS),
    # Chapter 13: refusals by 2 prompt versions and policy accuracy
    # by 2 index builds (during a rollout), 2 labels each; the 2
    # labels of groundedness and the 4 of intent, unsliced
    Budget(
        EVALUATION_RESULTS,
        (
            EVALUATION_NAME,
            EVALUATION_LABEL,
            PROMPT_VERSION,
            INDEX_VERSION,
        ),
        14,
    ),
)
