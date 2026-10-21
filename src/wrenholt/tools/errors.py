"""How a tool call can fail (Chapter 9): a closed, low-cardinality
set for error.type on execute_tool spans, like the gateway's."""

from enum import StrEnum


class ToolErrorType(StrEnum):
    INVALID_ARGUMENTS = "invalid_arguments"  # refused before running
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"  # connection failed or 5xx
    REJECTED = "rejected"  # the service said no: 4xx


class ToolError(Exception):
    def __init__(self, error_type: ToolErrorType, detail: str = ""):
        super().__init__(f"{error_type.value}: {detail}")
        self.error_type = error_type
        self.detail = detail
