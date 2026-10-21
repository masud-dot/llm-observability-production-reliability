"""Keyed pseudonyms (Chapter 7): HMAC-SHA256, never a plain hash.

A plain hash of an order ID is reversed by hashing every possible
ID; an HMAC cannot be computed without the key. Keys rotate: each
pseudonym names the key that made it, so a rotation is visible.
"""

import hashlib
import hmac
import os
from dataclasses import dataclass

# Development only. Production sets WRENHOLT_PSEUDONYM_KEYS from a
# secret store: "k2:<64 hex>,k1:<64 hex>", the current key first.
DEV_KEYS = "dev1:" + "6b" * 32


@dataclass(frozen=True)
class Keys:
    current: str
    secrets: dict[str, bytes]


def parse_keys(raw: str) -> Keys:
    secrets = {}
    for item in raw.split(","):
        kid, _, hexkey = item.strip().partition(":")
        secrets[kid] = bytes.fromhex(hexkey)
    current = raw.split(",")[0].split(":")[0].strip()
    return Keys(current, secrets)


def keys_from_env() -> Keys:
    return parse_keys(
        os.environ.get("WRENHOLT_PSEUDONYM_KEYS", DEV_KEYS)
    )


def pseudonym(kind: str, value: str, keys: Keys) -> str:
    key = keys.secrets[keys.current]
    mac = hmac.new(key, f"{kind}:{value}".encode(), hashlib.sha256)
    return f"{kind}:{keys.current}:{mac.hexdigest()[:12]}"
