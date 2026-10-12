"""Hash lab (Chapter 7): why pseudonyms are keyed (SIMULATED).

    uv run python scripts/hash_reversal.py

An order ID has a million possible values, so a plain SHA-256 of
one is reversed by hashing them all. A keyed HMAC cannot be
reproduced without the key, however small the input space.
"""

import hashlib
import hmac
import time

TARGET = "WG-100006"


def every_order_id() -> list[str]:
    return [f"WG-{n:06d}" for n in range(1_000_000)]


def reverse(
    digest: str, candidates: list[str], key: bytes | None
) -> tuple[str, int, float]:
    start = time.perf_counter()
    for tried, value in enumerate(candidates, 1):
        if key is None:
            guess = hashlib.sha256(value.encode()).hexdigest()
        else:
            mac = hmac.new(key, value.encode(), hashlib.sha256)
            guess = mac.hexdigest()
        if guess == digest:
            return value, tried, time.perf_counter() - start
    return "", len(candidates), time.perf_counter() - start


def main() -> None:
    ids = every_order_id()
    plain = hashlib.sha256(TARGET.encode()).hexdigest()
    secret = bytes.fromhex("6b" * 32)  # the defender's key
    keyed = hmac.new(
        secret, TARGET.encode(), hashlib.sha256
    ).hexdigest()
    found, tried, took = reverse(plain, ids, None)
    print("Plain hash against keyed pseudonym (order IDs, SIMULATED)")
    print(f"plain SHA-256 of {TARGET}, reversed by trying every ID:")
    print(f"  found {found} after {tried:,} hashes in {took:.2f} s")
    guess = bytes.fromhex("00" * 32)  # an attacker's best guess
    found, tried, took = reverse(keyed, ids, guess)
    print("HMAC-SHA256 pseudonym, same search with a guessed key:")
    print(f"  found {found or 'nothing'} after {tried:,} tries "
          f"in {took:.2f} s")  # fmt: skip
