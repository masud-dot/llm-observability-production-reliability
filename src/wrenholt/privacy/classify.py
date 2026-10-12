"""Find personal and secret data in text (Chapter 7).

Patterns, not a model: they find the structured identifiers
Wrenholt knows it handles. A name in free text is invisible to
them, which is why minimisation, not redaction, is the control.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    kind: str
    start: int
    end: int


PATTERNS = {
    "email": re.compile(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    ),
    "phone": re.compile(r"\+\d{1,3}(?:[ -]?\d){7,12}"),
    "order_id": re.compile(r"\bWG-\d{6}\b"),
    "card": re.compile(r"\b(?:\d[ -]?){12,18}\d\b"),
    "secret": re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
}
# Kinds replaced by a keyed pseudonym; the rest are masked outright.
IDENTIFIERS = frozenset({"email", "phone", "order_id"})


def luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def find(text: str) -> list[Finding]:
    """Every finding, earliest first, without overlaps."""
    found = []
    for kind, pattern in PATTERNS.items():
        for m in pattern.finditer(text):
            digits = re.sub(r"\D", "", m.group())
            if kind == "card" and not luhn(digits):
                continue
            found.append(Finding(kind, m.start(), m.end()))
    found.sort(key=lambda f: (f.start, -(f.end - f.start)))
    kept: list[Finding] = []
    for f in found:
        if not kept or f.start >= kept[-1].end:
            kept.append(f)
    return kept
