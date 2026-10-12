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


# The pinned specification the GenAI names come from.
GENAI_COMMIT: Final = "bcc7f9c2856fa7f4feb753f54d4ebba9455cc3dc"

# Opt-in content attributes. Wrenholt never emits them: content
# goes to the vault, by reference (Chapter 7).
CONTENT: Final = (
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.system_instructions",
    "gen_ai.tool.definitions",
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
)
