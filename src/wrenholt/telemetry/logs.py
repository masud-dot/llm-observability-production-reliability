"""Structured stdout logs that carry trace IDs (Chapter 6).

Records exported over OTLP carry trace context already; these JSON
lines give the same join key to anything that reads stdout.
"""

import json
import logging
from datetime import UTC, datetime

from opentelemetry import trace


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, object] = {
            "time": datetime.fromtimestamp(
                record.created, UTC
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = trace.get_current_span().get_span_context()
        if context.is_valid:
            line["trace_id"] = format(context.trace_id, "032x")
            line["span_id"] = format(context.span_id, "016x")
        for key, value in vars(record).items():
            if key.startswith("wrenholt."):
                line[key] = value
        return json.dumps(line)


def to_stdout(name: str = "wrenholt") -> None:
    """Send one logger tree to stdout as JSON lines, once."""
    logger = logging.getLogger(name)
    if any(
        isinstance(h.formatter, JsonFormatter)
        for h in logger.handlers
    ):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
