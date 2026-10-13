"""What an evaluator may see of an answer, in process (Chapter 13)."""

from contextvars import ContextVar

# The passages the request's retrieval found, set by the retriever
# Linnet uses. Their text never leaves the process.
PASSAGES: ContextVar[tuple[str, ...]] = ContextVar(
    "passages", default=()
)
