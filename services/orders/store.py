"""Orders and refunds for Wrenholt's orders service.

The 5,000 orders are generated from a fixed seed, so every reader
gets the same data. Names, emails, phone numbers and addresses are
PII-shaped but invented, for the redaction tests in Chapter 7.
"""

import hashlib
import json
import random
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import date, timedelta

SEED = 20260930
ORDER_COUNT = 5000
CUSTOMER_COUNT = 1000
STATUSES = (
    "placed",
    "shipped",
    "delivered",
    "returned",
    "refunded",
    "cancelled",
)
WEIGHTS = (10, 15, 55, 8, 7, 5)
FIRST = ("Ada", "Bram", "Cleo", "Dev", "Esme", "Finn", "Greta")
LAST = ("Archer", "Brook", "Calloway", "Dunmore", "Ellery", "Fry")
STREETS = ("Mill", "Church", "Station", "Orchard", "Willow")
TOWNS = ("Ashby", "Brackley", "Corwen", "Dunholm", "Fenwick")
FIRST_DAY = date(2026, 3, 1)
DAYS = 214  # 1 March to 30 September 2026


@dataclass(frozen=True)
class Order:
    order_id: str
    status: str
    customer: str
    email: str
    phone: str
    address: str
    placed_on: str
    total_minor: int


@dataclass(frozen=True)
class Refund:
    refund_id: str
    order_id: str
    amount_minor: int
    replayed: bool


class RefundError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def generate_orders() -> list[Order]:
    rng = random.Random(SEED)
    people = []
    for c in range(CUSTOMER_COUNT):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        street = f"{rng.randint(1, 180)} {rng.choice(STREETS)} Lane"
        people.append(
            (
                f"{first} {last}",
                f"{first}.{last}.{c:04d}@example.com".lower(),
                f"+44 7700 9{c:05d}",
                f"{street}, {rng.choice(TOWNS)}",
            )
        )
    orders = []
    for i in range(ORDER_COUNT):
        name, email, phone, address = people[
            rng.randrange(CUSTOMER_COUNT)
        ]
        placed = FIRST_DAY + timedelta(days=rng.randrange(DAYS))
        orders.append(
            Order(
                order_id=f"WG-{100000 + i}",
                status=rng.choices(STATUSES, WEIGHTS)[0],
                customer=name,
                email=email,
                phone=phone,
                address=address,
                placed_on=placed.isoformat(),
                total_minor=rng.randrange(899, 45000),
            )
        )
    return orders


def dataset_hash(orders: list[Order]) -> str:
    """First 16 hex digits of SHA-256 over the canonical rows."""
    rows = "\n".join(
        json.dumps(asdict(o), sort_keys=True) for o in orders
    )
    return hashlib.sha256(rows.encode("utf-8")).hexdigest()[:16]


class OrderStore:
    """SQLite in memory; one lock, so each refund is atomic."""

    def __init__(self, orders: list[Order]) -> None:
        self._db = sqlite3.connect(
            ":memory:", check_same_thread=False
        )
        self._lock = threading.Lock()
        self._db.execute(
            "CREATE TABLE orders (order_id TEXT PRIMARY KEY,"
            " status TEXT, customer TEXT, email TEXT, phone TEXT,"
            " address TEXT, placed_on TEXT, total_minor INTEGER)"
        )
        self._db.execute(
            "CREATE TABLE refunds (idem_key TEXT PRIMARY KEY,"
            " refund_id TEXT, order_id TEXT, amount_minor INTEGER)"
        )
        self._db.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [tuple(asdict(o).values()) for o in orders],
        )
        self._db.commit()

    def count(self) -> int:
        with self._lock:
            row = self._db.execute("SELECT COUNT(*) FROM orders")
            return int(row.fetchone()[0])

    def get(self, order_id: str) -> Order | None:
        with self._lock:
            return self._get(order_id)

    def _get(self, order_id: str) -> Order | None:
        row = self._db.execute(
            "SELECT * FROM orders WHERE order_id = ?", (order_id,)
        ).fetchone()
        return Order(*row) if row else None

    def refund(self, key: str, order_id: str, amount: int) -> Refund:
        with self._lock:
            seen = self._db.execute(
                "SELECT refund_id, order_id, amount_minor"
                " FROM refunds WHERE idem_key = ?",
                (key,),
            ).fetchone()
            if seen:
                if (seen[1], seen[2]) != (order_id, amount):
                    raise RefundError(
                        409, "key reused for another refund"
                    )
                return Refund(
                    seen[0], order_id, amount, replayed=True
                )
            order = self._get(order_id)
            if order is None:
                raise RefundError(404, "unknown order")
            if order.status != "delivered":
                raise RefundError(409, f"order is {order.status}")
            if not 0 < amount <= order.total_minor:
                raise RefundError(422, "amount out of range")
            done = self._db.execute("SELECT COUNT(*) FROM refunds")
            refund_id = f"RF-{done.fetchone()[0] + 1:06d}"
            self._db.execute(
                "INSERT INTO refunds VALUES (?, ?, ?, ?)",
                (key, refund_id, order_id, amount),
            )
            self._db.execute(
                "UPDATE orders SET status = 'refunded'"
                " WHERE order_id = ?",
                (order_id,),
            )
            self._db.commit()
            return Refund(refund_id, order_id, amount, replayed=False)
