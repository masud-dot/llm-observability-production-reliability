"""What the gateway sends and returns, independent of provider."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Message:
    role: str
    content: str


@dataclass(frozen=True)
class Completion:
    text: str
    status: int
    response_model: str
    response_id: str
    finish_reasons: tuple[str, ...]
    input_tokens: int | None
    output_tokens: int | None
