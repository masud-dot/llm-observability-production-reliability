"""What the gateway sends and returns, independent of provider."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    """A tool call the model asked for (Chapter 9). The arguments
    are the model's JSON text, unchecked until the tool runs."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ToolSpec:
    """A tool offered to the model: its JSON Schema parameters."""

    name: str
    description: str
    parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Message:
    role: str
    content: str
    # Chapter 9: an assistant turn that called tools, and the tool
    # turn that answers one call.
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str = ""


@dataclass(frozen=True)
class Usage:
    """Tokens one completed call used, as the provider reported them
    (Chapter 11). input includes cache_read; None means the provider
    did not say."""

    input: int
    output: int
    cache_read: int | None = None


@dataclass(frozen=True)
class Completion:
    text: str
    status: int
    response_model: str
    response_id: str
    finish_reasons: tuple[str, ...]
    input_tokens: int | None
    output_tokens: int | None
    tool_calls: tuple[ToolCall, ...] = ()  # Chapter 9
    cache_read_tokens: int | None = None  # Chapter 11

    @property
    def usage(self) -> Usage | None:
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return Usage(
            self.input_tokens,
            self.output_tokens,
            self.cache_read_tokens,
        )
