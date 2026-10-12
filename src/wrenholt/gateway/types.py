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
class Completion:
    text: str
    status: int
    response_model: str
    response_id: str
    finish_reasons: tuple[str, ...]
    input_tokens: int | None
    output_tokens: int | None
    tool_calls: tuple[ToolCall, ...] = ()  # Chapter 9
