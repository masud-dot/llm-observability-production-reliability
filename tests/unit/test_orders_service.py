"""Orders service: deterministic data, lookups, idempotent refunds."""

import json
import time
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
        # Since Chapter 9 refunds go item by item: a new key is a
        # new refund, up to what is left of the order's total.
        total = next(
            o.total_minor for o in ORDERS if o.order_id == DELIVERED
        )
        second = call(f"{base}/refunds", refund, key="k-2")
        assert second[0] == 201
        assert second[1]["refund_id"] != first[1]["refund_id"]
        assert call(f"{base}/orders/{DELIVERED}")[1]["status"] == (
            "part_refunded"
        )
        rest = {"order_id": DELIVERED, "amount_minor": total - 1000}
        too_much = {**rest, "amount_minor": total - 999}
        assert call(f"{base}/refunds", too_much, key="k-3")[0] == 422
        assert call(f"{base}/refunds", rest, key="k-4")[0] == 201
        assert call(f"{base}/orders/{DELIVERED}")[1]["status"] == (
            "refunded"
        )
        assert call(f"{base}/refunds", refund, key="k-5")[0] == 409


def test_a_slow_commit_still_commits() -> None:
    """FS-07's fault: the answer to a new refund is late, the
    refund is not; a replay of the same key is answered at once."""
    store = OrderStore(ORDERS)
    app = create_app(store, Faults(slow_commit_s=0.3))
    refund = {"order_id": DELIVERED, "amount_minor": 500}
    with serve(app) as base:
        start = time.monotonic()
        first = call(f"{base}/refunds", refund, key="k-1")
        slow = time.monotonic() - start
        start = time.monotonic()
        again = call(f"{base}/refunds", refund, key="k-1")
        quick = time.monotonic() - start
    assert (first[0], again[0]) == (201, 200)
    assert slow >= 0.3 > quick
    assert store.refunds_for(DELIVERED) == [first[1]["refund_id"]]


def test_fault_injection_fails_every_nth_request() -> None:
    app = create_app(OrderStore(ORDERS), Faults(fail_every=3))
    with serve(app) as base:
        codes = [
            call(f"{base}/orders/{DELIVERED}")[0] for _ in range(6)
        ]
    assert codes == [200, 200, 503, 200, 200, 503]
