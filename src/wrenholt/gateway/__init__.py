"""Linnet's LLM gateway (Chapter 4)."""

from wrenholt.gateway.client import Gateway, StreamResult
from wrenholt.gateway.errors import ErrorType, ProviderError
from wrenholt.gateway.policy import RetryPolicy
from wrenholt.gateway.routing import Route
from wrenholt.gateway.types import (
    Completion,
    Message,
    ToolCall,
    ToolSpec,
)

__all__ = [
    "Completion",
    "ErrorType",
    "Gateway",
    "StreamResult",
    "Message",
    "ProviderError",
    "RetryPolicy",
    "Route",
    "ToolCall",
    "ToolSpec",
]
