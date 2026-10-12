"""Finding personal data, and pseudonyms that cannot be reversed."""

import hashlib

from wrenholt.labs.hash_lab import TARGET, every_order_id, reverse
from wrenholt.privacy.classify import find, luhn
from wrenholt.privacy.pseudonym import parse_keys, pseudonym

SENTENCE = (
    "I'm Esme Fry (esme.fry.0628@example.com, +44 7700 900628). "
    "Order WG-100006, card 4111 1111 1111 1111, key sk-test12345678"
)


def test_every_structured_kind_is_found_once() -> None:
    kinds = [f.kind for f in find(SENTENCE)]
    assert kinds == ["email", "phone", "order_id", "card", "secret"]


def test_a_name_is_not_found() -> None:
    """The limit that makes minimisation the control."""
    assert find("I'm Esme Fry") == []


def test_cards_must_pass_luhn() -> None:
    assert luhn("4111111111111111")
    assert find("card 4111 1111 1111 1112") == []


def test_pseudonyms_are_stable_keyed_and_name_their_key() -> None:
    one = parse_keys("k1:" + "11" * 32)
    two = parse_keys("k2:" + "22" * 32 + ",k1:" + "11" * 32)
    a = pseudonym("order_id", TARGET, one)
    assert a == pseudonym("order_id", TARGET, one)
    assert a.startswith("order_id:k1:")
    rotated = pseudonym("order_id", TARGET, two)
    assert rotated.startswith("order_id:k2:") and rotated != a


def test_plain_hash_reverses_and_keyed_does_not() -> None:
    ids = every_order_id()
    plain = hashlib.sha256(TARGET.encode()).hexdigest()
    assert reverse(plain, ids, None)[0] == TARGET
    keyed = pseudonym(
        "order_id", TARGET, parse_keys("k:" + "6b" * 32)
    )
    digest = keyed.split(":")[-1]
    assert reverse(digest, ids[:200_000], bytes(32))[0] == ""
