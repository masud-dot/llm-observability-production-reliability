"""Embeddings for queries and articles (Chapter 9).

SIMULATED: feature hashing stands in for an embedding model. Each
word lands in one of 4,096 slots with a sign, both chosen by a hash
salted with the embedder's name. Two embedders therefore give
vectors of the same size in unrelated spaces: comparing one with
the other raises nothing and finds nothing (FS-08).
"""

import hashlib
import math
import re
from dataclasses import dataclass

Vector = dict[int, float]  # sparse: slot to weight, unit length
STOP = frozenset(
    "a an and are as at be by can do does for from have how i if in "
    "is it its my of on or our the their this to was we what when "
    "where which will with you your".split()
)


def stem(word: str) -> str:
    """A crude stemmer: "returned", "returns" and "return" agree."""
    for ending in ("ing", "ed", "es", "s"):
        if len(word) > len(ending) + 2 and word.endswith(ending):
            word = word[: -len(ending)]
            break
    return word[:-1] if len(word) > 3 and word.endswith("e") else word


def words(text: str) -> list[str]:
    """Lower-case word stems, without stop words."""
    found = re.findall(r"[a-z0-9]+", text.lower())
    return [stem(w) for w in found if w not in STOP]


@dataclass(frozen=True)
class Embedder:
    name: str  # the model name telemetry reports
    salt: str
    dimensions: int = 4096
    provider: str = "wrenholt.local"  # in-process, no gateway

    def embed(self, text: str) -> Vector:
        vector: Vector = {}
        for word in words(text):
            digest = hashlib.blake2b(
                f"{self.salt}:{word}".encode(), digest_size=8
            ).digest()
            slot = int.from_bytes(digest[:4]) % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[slot] = vector.get(slot, 0.0) + sign
        norm = math.sqrt(sum(v * v for v in vector.values())) or 1.0
        return {k: v / norm for k, v in vector.items()}


def similarity(a: Vector, b: Vector) -> float:
    """Cosine similarity of two unit vectors."""
    if len(b) < len(a):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


EMBEDDERS = {
    "wrenholt-embed-1": Embedder("wrenholt-embed-1", "e1"),
    "wrenholt-embed-2": Embedder("wrenholt-embed-2", "e2"),
}
