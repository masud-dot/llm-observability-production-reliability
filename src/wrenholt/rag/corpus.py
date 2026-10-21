"""Wrenholt's help-centre corpus (Chapter 9): synthetic, versioned.

About 400 articles from a fixed seed, so every reader gets the
same corpus. A few articles have two versions with effective
dates: a snapshot taken on a date holds the versions in force
then, which is how a stale index is modelled (FS-09).
"""

import hashlib
import json
import random
from dataclasses import asdict, dataclass

SEED = 20261009
TODAY = "2026-09-30"


@dataclass(frozen=True)
class Article:
    id: str
    version: str  # slug and effective month: "returns-2026-03"
    effective: str  # ISO date the version took effect
    title: str
    text: str


# Policies with history. Chapter 2's FS-09 turns on the first one:
# the returns window fell from 60 to 30 days on 1 March 2026.
RETURNS = (
    "2025-09-01",
    "2026-03-01",
)
POLICIES = (
    ("returns", "Returns policy", RETURNS[0],
     "Most items can be returned within 60 days of delivery for a "
     "full refund. Items must be unused and in their original "
     "packaging. Start a return from My orders and we email a "
     "prepaid label."),
    ("returns", "Returns policy", RETURNS[1],
     "Most items can be returned within 30 days of delivery for a "
     "full refund. Items must be unused and in their original "
     "packaging. Start a return from My orders and we email a "
     "prepaid label."),
    ("refund-timing", "When refunds arrive", "2025-11-03",
     "Refunds reach your card within five working days of your "
     "return reaching our warehouse. Partial refunds for single "
     "items follow the same timetable."),
    ("damaged", "Damaged or faulty goods", "2025-10-06",
     "Tell us within 14 days if something arrives damaged. Send a "
     "photo from My orders and we replace or refund it without "
     "needing it back."),
    ("order-tracking", "Tracking an order", "2026-01-12",
     "Every order shows its status under My orders: placed, "
     "shipped, delivered, returned or refunded. Tracking links "
     "appear once the courier collects the parcel."),
    ("cancel", "Cancelling an order", "2026-02-02",
     "You can cancel an order from My orders until it ships. Once "
     "shipped, refuse the delivery or start a return instead."),
)  # fmt: skip
PRODUCTS = (
    "folding garden chair", "hardwood bench", "camping tent",
    "solar lantern", "picnic blanket", "enamel kettle",
    "cast iron skillet", "wool throw", "jute rug", "rattan basket",
    "bird feeder", "potting bench", "hose reel", "garden kneeler",
    "fire pit", "hammock", "parasol", "cool box", "trail rucksack",
    "sleeping bag", "camping stove", "lantern hook", "log store",
    "plant stand", "watering can", "doormat", "storage trunk",
    "reading lamp", "bedside table", "linen cushion",
    "oak shelf", "coat rack", "umbrella stand", "herb planter",
    "compost bin", "garden trug", "wind chime", "sun lounger",
    "bistro table", "outdoor heater",
)  # fmt: skip
KINDS = (
    ("care", "caring for your {p}",
     "Wipe the {p} with a damp cloth and dry it fully. Store it "
     "somewhere dry over winter, and oil any hinges every {n} "
     "months."),
    ("assembly", "assembling your {p}",
     "The {p} arrives flat packed with every fixing included. "
     "Assembly takes about {n} minutes with two people and the "
     "supplied key."),
    ("warranty", "warranty for your {p}",
     "Your {p} carries a {n} year guarantee against defects in "
     "materials and workmanship. Wear and weather damage are not "
     "covered."),
    ("parts", "spare parts for your {p}",
     "Spare feet, fixings and covers for the {p} can be ordered "
     "from the parts page. Most parts ship within {n} working "
     "days."),
    ("safety", "using your {p} safely",
     "Keep the {p} on level ground and check every fixing before "
     "use. Do not exceed the rated load of {n} kilograms."),
    ("sizing", "sizes of the {p}",
     "The {p} comes in {n} sizes. Each listing shows the folded "
     "and open measurements in centimetres."),
    ("storage", "storing your {p}",
     "Clean the {p} before storing it and keep it covered. A "
     "breathable cover is sold separately for about {n} pounds."),
    ("troubleshooting", "fixing a wobbly {p}",
     "If the {p} wobbles, loosen every bolt, stand it on a flat "
     "floor and tighten them again in a cross pattern, {n} turns "
     "each."),
    ("colours", "colours of the {p}",
     "The {p} is made in {n} colours. Colours on screen can differ "
     "slightly from the finished piece."),
)  # fmt: skip
TOWNS = (
    "Ashby", "Brackley", "Corwen", "Dunholm", "Fenwick", "Garth",
    "Hollin", "Ickford", "Jarrow", "Kelso", "Lydford", "Marden",
    "Nairn", "Oakham", "Penrith", "Quarley", "Rydal", "Selby",
    "Tetbury", "Ulverston", "Ventnor", "Wareham", "Yarm", "Zennor",
    "Alston", "Bampton", "Cowes", "Diss", "Eyam", "Frome",
    "Goole", "Hexham", "Ilsley", "Jedburgh", "Keswick", "Ledbury",
    "Malton", "Newent", "Olney", "Padstow",
)  # fmt: skip


def articles() -> list[Article]:
    """Every version of every article, oldest version first."""
    rng = random.Random(SEED)
    out: list[Article] = []
    ids: dict[str, str] = {}  # slug: article ID

    def add(slug: str, title: str, effective: str, text: str) -> None:
        # Versions of one slug share the ID of its first version.
        aid = ids.setdefault(slug, f"HC-{len(ids) + 1:04d}")
        version = f"{slug}-{effective[:7]}"
        out.append(Article(aid, version, effective, title, text))

    for slug, title, effective, text in POLICIES:
        add(slug, title, effective, text)
    for product in PRODUCTS:
        for kind, title, text in KINDS:
            month, day = rng.randint(1, 12), rng.randint(1, 28)
            effective = f"2025-{month:02d}-{day:02d}"
            n = rng.randint(2, 12)
            slug = f"{kind}-{product.replace(' ', '-')}"
            add(
                slug,
                title.format(p=product).capitalize(),
                effective,
                text.format(p=product, n=n),
            )
    for town in TOWNS:
        days = rng.randint(2, 5)
        add(
            f"delivery-{town.lower()}",
            f"Delivery to {town}",
            "2026-01-05",
            f"Standard delivery to {town} takes {days} working days. "
            "Next-day delivery is available for orders placed "
            "before noon.",
        )
    return out


def snapshot(as_of: str = TODAY) -> list[Article]:
    """The corpus as it stood on a date: each article's latest
    version that had taken effect by then."""
    latest: dict[str, Article] = {}
    for a in articles():
        if a.effective <= as_of:
            latest[a.id] = a  # versions are oldest first
    return sorted(latest.values(), key=lambda a: a.id)


def corpus_hash(items: list[Article]) -> str:
    """First 16 hex digits of SHA-256 over the canonical rows."""
    rows = "\n".join(
        json.dumps(asdict(a), sort_keys=True) for a in items
    )
    return hashlib.sha256(rows.encode("utf-8")).hexdigest()[:16]
