"""The mock model's choices once tools are in play (Chapter 9).

SIMULATED: rules, not a model. Offered tools, the mock asks for
what a careful assistant would do next: look the order up, refund
it if the customer asked and the order allows, then finish. A
refund that failed in transit is asked for again, as models do.
Offered no tools, it answers from the notes Linnet added: the
facts its tools found and the policy passages it retrieved.
"""

import json
import re
from typing import Any

ORDER = re.compile(r"\bWG-\d{6}\b")
POUNDS = re.compile(r"£(\d+)\.(\d{2})")
WINDOW = re.compile(r"returned within (\d+) days")
REFUND_NOTE = re.compile(r"^Refund (RF-\d{6}): £(\d+\.\d{2})")
ORDER_NOTE = re.compile(
    r"^Order (WG-\d{6}): (\w+), placed on ([-\d]+)"
)
RETRY = {"timeout", "unavailable"}
Call = dict[str, Any]


def call(arrival: int, n: int, name: str, args: Call) -> Call:
    return {
        "id": f"call_{arrival:06d}_{n}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def results(messages: list[Any]) -> dict[str, list[Call]]:
    """Each tool's results so far, oldest first, by tool name."""
    names = {
        c["id"]: c["function"]["name"]
        for m in messages
        for c in (m.tool_calls or ())
    }
    found: dict[str, list[Call]] = {}
    for m in messages:
        if m.role == "tool" and m.tool_call_id in names:
            name = names[m.tool_call_id]
            found.setdefault(name, []).append(json.loads(m.content))
    return found


def decide(messages: list[Any], arrival: int) -> list[Call]:
    question = next(m.content for m in messages if m.role == "user")
    order = ORDER.search(question or "")
    done = results(messages)
    if order is None:
        return [call(arrival, 0, "finish", {})]
    looked = done.get("lookup_order", [])
    if not looked:
        lookup: Call = {"order_id": order.group()}
        return [call(arrival, 0, "lookup_order", lookup)]
    facts = looked[-1]
    refunds = done.get("issue_refund", [])
    wants = "refund" in question.lower()
    open_order = facts.get("status") in ("delivered", "part_refunded")
    retry = bool(refunds) and refunds[-1].get("error") in RETRY
    if wants and open_order and (not refunds or retry):
        pounds = POUNDS.search(question)
        amount = (
            int(pounds.group(1)) * 100 + int(pounds.group(2))
            if pounds
            else facts["total_minor"]
        )
        refund: Call = {
            "order_id": order.group(),
            "amount_minor": amount,
        }
        return [call(arrival, 0, "issue_refund", refund)]
    return [call(arrival, 0, "finish", {})]


def from_notes(question: str, notes: list[str]) -> str | None:
    """An answer built from Linnet's notes, or None to fall back to
    the keyword answers."""
    for note in notes:
        refunded = REFUND_NOTE.search(note)
        if refunded:
            return (
                f"Your refund {refunded.group(1)} of "
                f"£{refunded.group(2)} is on its way. Refunds reach "
                "your card within five working days."
            )
        if note.startswith("Refund not confirmed"):
            return (
                "I could not confirm your refund just now. A member "
                "of the team will check it and email you."
            )
    for note in notes:
        order = ORDER_NOTE.search(note)
        if order:
            status = order.group(2).replace("_", " ")
            return (
                f"Order {order.group(1)} is {status}. It was "
                f"placed on {order.group(3)}."
            )
    if "return" in question.lower():
        for note in notes:
            window = WINDOW.search(note)
            if window:
                days = window.group(1)
                return (
                    f"Most items can be returned within {days} days."
                )
    return None
