"""Orders service: deterministic data, lookups, idempotent refunds."""

import json
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from services.orders.app import create_app
from services.orders.faults import Faults
from services.orders.store import (
    ORDER_COUNT,
    OrderStore,
    dataset_hash,
    generate_orders,
)
from services.serving import serve

ROOT = Path(__file__).resolve().parents[2]
ORDERS = generate_orders()
DELIVERED = "WG-100006"  # first delivered order in the dataset


def call(
    url: str, body: dict[str, object] | None = None, key: str = ""
) -> tuple[int, dict[str, object]]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data)
    request.add_header("Content-Type", "application/json")
    if key:
        request.add_header("Idempotency-Key", key)
    try:
        with urllib.request.urlopen(request, timeout=5) as resp:
            return int(resp.status), json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_dataset_matches_its_recorded_hash() -> None:
    hashes = tomllib.loads((ROOT / "data/hashes.toml").read_text())
    assert len(ORDERS) == ORDER_COUNT == hashes["orders"]["count"]
    assert dataset_hash(ORDERS) == hashes["orders"]["sha256_16"]
    assert all(o.email.endswith("@example.com") for o in ORDERS)


def test_lookup_and_refund_rules() -> None:
    with serve(create_app(OrderStore(ORDERS))) as base:
        status, order = call(f"{base}/orders/{DELIVERED}")
        assert (status, order["status"]) == (200, "delivered")
        assert call(f"{base}/orders/WG-999999")[0] == 404
        refund = {"order_id": DELIVERED, "amount_minor": 500}
        assert call(f"{base}/refunds", refund)[0] == 400  # no key
        first = call(f"{base}/refunds", refund, key="k-1")
        again = call(f"{base}/refunds", refund, key="k-1")
        assert first[0] == 201 and again[0] == 200
        assert first[1]["refund_id"] == again[1]["refund_id"]
        assert again[1]["replayed"] is True
        other = {"order_id": DELIVERED, "amount_minor": 600}
        assert call(f"{base}/refunds", other, key="k-1")[0] == 409
        # A new key cannot refund the same order twice either.
        assert call(f"{base}/refunds", refund, key="k-2")[0] == 409


def test_fault_injection_fails_every_nth_request() -> None:
    app = create_app(OrderStore(ORDERS), Faults(fail_every=3))
    with serve(app) as base:
        codes = [
            call(f"{base}/orders/{DELIVERED}")[0] for _ in range(6)
        ]
    assert codes == [200, 200, 503, 200, 200, 503]
