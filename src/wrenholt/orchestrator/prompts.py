"""Versioned prompts (Chapter 6).

A prompt's version is declared; its hash is computed, so an edit
made without a new version still shows in every bundle.
"""

import hashlib
from dataclasses import dataclass

from wrenholt.orchestrator.baseline import SYSTEM_PROMPT


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    text: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()[:16]


SUPPORT = Prompt("linnet.support", "1", SYSTEM_PROMPT)
