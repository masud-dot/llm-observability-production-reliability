"""The telemetry contract's privacy column (Chapter 7).

Every key Wrenholt exports has a data class, and every class has a
handling rule. A key that appears in exported telemetry without a
class fails the privacy tests, so new instrumentation is reviewed.
"""

from enum import StrEnum

from wrenholt.telemetry import conventions as c


class DataClass(StrEnum):
    OPERATIONAL = "operational"
    IDENTIFIER = "identifier"
    PERSONAL = "personal"
    CONTENT = "content"
    SECRET = "secret"


# How each class is handled: (handling, retention, who reads).
HANDLING = {
    DataClass.OPERATIONAL: (
        "exported as is", "metrics 30 days; traces, logs 14 days",
        "on-call",
    ),
    DataClass.IDENTIFIER: (
        "exported; personal ones only as keyed pseudonyms",
        "as its signal", "on-call",
    ),
    DataClass.PERSONAL: (
        "never exported raw: pseudonymised or masked first",
        "not retained in telemetry", "nobody",
    ),
    DataClass.CONTENT: (
        "vault only, by reference, when capture is on",
        "72 hours", "investigators, audited",
    ),
    DataClass.SECRET: (
        "never stored: masked", "not retained", "nobody",
    ),
}  # fmt: skip

_OPERATIONAL = {
    # GenAI and core names from the registry, except the response ID
    *(n.name for n in c.REGISTRY),
    # resource attributes
    "service.name", c.SERVICE_NAMESPACE, c.SERVICE_VERSION,
    c.DEPLOYMENT_ENVIRONMENT, "telemetry.sdk.language",
    "telemetry.sdk.name", "telemetry.sdk.version",
    # HTTP instrumentation
    "http.request.method", "http.route", "url.scheme",
    "network.protocol.version",
    # log records' code location
    "code.file.path", "code.function.name", "code.line.number",
    # Chapter 6 and 7 book names
    c.REPRO_BUNDLE, c.PRIVACY_KIND, c.PRIVACY_WHERE,
}  # fmt: skip
_IDENTIFIER = {
    c.RESPONSE_ID, c.CONTENT_REF,
    # the calling service; personal if the callers are people
    "client.address", "client.port", "network.peer.address",
    "network.peer.port", "user_agent.original",
    # carry order IDs, exported only as keyed pseudonyms
    "url.path", "url.full",
}  # fmt: skip

FIELDS: dict[str, DataClass] = {
    **{k: DataClass.OPERATIONAL for k in _OPERATIONAL - _IDENTIFIER},
    **{k: DataClass.IDENTIFIER for k in _IDENTIFIER},
}
# Never an exported key: these live only in the vault or nowhere.
NEVER_EXPORTED = {
    "question": DataClass.CONTENT,
    "answer": DataClass.CONTENT,
    "customer.name": DataClass.PERSONAL,
    "customer.email": DataClass.PERSONAL,
    "customer.phone": DataClass.PERSONAL,
    "customer.address": DataClass.PERSONAL,
    "provider.api_key": DataClass.SECRET,
}
