"""Cost per resolved ticket, the labs' numbers and the latency
decomposition (Chapter 11). Every worked number in the chapter."""

from collections import Counter
from decimal import Decimal

import pytest

from wrenholt.economics import (
    Ticket,
    Timed,
    bucket_counts,
    cost_per_resolved,
    decompose,
    from_spans,
    histogram_quantile,
    tickets,
)
from wrenholt.labs import fs12_lab, fs13_lab
from wrenholt.labs.cost_lab import CAP, V2, measure
from wrenholt.orchestrator.prompts import SUPPORT
from wrenholt.slo.fs09 import normal_hour
from wrenholt.slo.request_map import load_request_map
from wrenholt.telemetry import conventions as c

# Each journey's answer on mock-a-fast, warm cache (Table 11.2).
PER_ANSWER = {
    "policy_question": Decimal("0.0000433"),
    "order_status": Decimal("0.0001883"),
    "refund_request": Decimal("0.0003336"),
}


def test_the_normal_hour_by_hand() -> None:
    hour = Counter(e.journey for e in normal_hour())
    assert hour == Counter(
        policy_question=60, order_status=30, refund_request=30
    )
    total = sum(
        (PER_ANSWER[j] * n for j, n in hour.items()), Decimal(0)
    )
    assert total == Decimal("0.018255")
    found = tickets(normal_hour(), PER_ANSWER)
    assert sum(t.resolved for t in found) == 114  # 6 escalated
    per = cost_per_resolved(found)
    assert per == total / 114
    assert round(per * 1000, 2) == Decimal("0.16")  # a thousand


def test_failures_raise_the_cost_per_resolved_ticket() -> None:
    paid = [Ticket("refund_request", Decimal("1"), True)] * 9
    once = cost_per_resolved(paid)
    failed = [*paid, Ticket("refund_request", Decimal("1"), False)]
    assert cost_per_resolved(failed) == Decimal(10) / 9 > once
    with pytest.raises(ValueError):
        cost_per_resolved([Ticket("x", Decimal("1"), False)])


def test_the_peak_hour_and_the_limit() -> None:
    per_answer = Decimal("0.018255") / 120
    peak = per_answer * 40 * 3600
    assert peak == Decimal("21.906")
    assert round(peak / 60, 3) == Decimal("0.365")  # of $60 an hour
    fallback = peak * 5
    assert fallback == Decimal("109.530")
    assert round(60 / fallback * 60) == 33  # minutes to the limit


def test_the_histogram_p99_is_an_estimate_inside_a_bucket() -> None:
    bounds = c.TOKEN_BUCKETS
    v1 = [8] * 60 + [5, 4, 9] * 30 + [5, 7, 4, 17] * 30
    v2 = [88] * 60 + [5, 4, 89] * 30 + [5, 7, 4, 97] * 30
    assert len(v1) == len(v2) == 270
    p1 = histogram_quantile(0.99, bounds, bucket_counts(v1, bounds))
    p2 = histogram_quantile(0.99, bounds, bucket_counts(v2, bounds))
    assert round(p1, 2) == 59.68  # though no call wrote over 17
    assert round(p2, 2) == 251.68  # though none wrote over 97
    assert sum(n > 64 for n in v1) == 0
    assert sum(n > 64 for n in v2) == 120


def test_a_verbose_answer_is_a_slow_answer() -> None:
    assert fs12_lab.streamed_s(8) == pytest.approx(1.24)
    assert fs12_lab.streamed_s(88) == pytest.approx(10.84)
    assert fs12_lab.streamed_s(88) > load_request_map().deadline_s


# A streamed refund answer, SIMULATED (Table 11.3).
REFUND = [
    Timed("retrieval", 0.32),
    Timed("chat", 0.9),  # decide: look the order up
    Timed("tool", 0.27),
    Timed("chat", 1.6, waited=0.5),  # decide: refund, after a 429
    Timed("tool", 0.41),
    Timed("chat", 0.8),  # decide: finish
    Timed("chat", 3.2, first_chunk=1.1),  # the streamed answer
]


def test_the_decomposition_worked_example() -> None:
    parts = decompose(7.8, REFUND)
    assert parts == pytest.approx(
        {
            "queueing": 0.5,
            "retrieval": 0.32,
            "tools": 0.68,
            "model": 2.8,
            "first_chunk": 1.1,
            "generation": 2.1,
            "other": 0.3,
        }
    )
    assert sum(parts.values()) == pytest.approx(7.8)
    # Every step the request map budgets fits; it has no step for
    # the deciding calls, the largest part.
    steps = {s.id: s.budget_s for s in load_request_map().steps}
    assert parts["retrieval"] <= steps["retrieval"] == 0.6
    assert (
        parts["tools"]
        <= steps["order_lookup"] + steps["refund_write"]
    )
    assert parts["first_chunk"] <= steps["model_first_chunk"] == 2.5
    assert parts["generation"] <= steps["stream_rest"] == 4.0
    assert max(parts, key=lambda k: parts[k]) == "model"


def test_the_decomposition_of_a_real_trace() -> None:
    m = measure()
    spans = m.telemetry.spans.get_finished_spans()
    agents = [s for s in spans if s.name.startswith(c.INVOKE_AGENT)]
    last = agents[-1].context
    assert last is not None
    refund = [s for s in spans if s.context.trace_id == last.trace_id]
    parts = from_spans(refund)
    assert parts["tools"] > 0 and parts["retrieval"] > 0
    assert parts["model"] > 0 and parts["queueing"] == 0
    assert parts["first_chunk"] == parts["generation"] == 0  # whole
    total = sum(parts.values())
    assert total == pytest.approx(
        ((agents[-1].end_time or 0) - (agents[-1].start_time or 0))
        / 1e9
    )


def test_table_11_2() -> None:
    # What one answer of each journey used: calls, input tokens (and
    # how many came from the cache), output tokens.
    brief, thorough = measure(), measure(prompt=V2)
    used = {
        j: (
            b.calls,
            b.input_tokens,
            sum(
                int(str((s.attributes or {})[c.CACHE_READ_TOKENS]))
                for s in brief.calls[j]
            ),
            b.output_tokens,
            thorough.spend[j].output_tokens,
        )
        for j, b in brief.spend.items()
    }
    assert used == {
        "policy_question": (1, 86, 13, 8, 88),
        "order_status": (3, 428, 39, 18, 98),
        "refund_request": (4, 741, 52, 33, 113),
    }


def test_fs12_lab() -> None:
    before, after = fs12_lab.run(SUPPORT), fs12_lab.run(V2)
    assert before.per_answer == PER_ANSWER
    assert after.per_answer == {
        "policy_question": Decimal("0.0001713"),
        "order_status": Decimal("0.0003163"),
        "refund_request": Decimal("0.0004616"),
    }
    assert before.hour == Decimal("0.018255")
    assert after.hour == Decimal("0.033615")
    assert round(after.peak, 2) == Decimal("40.34")
    assert len(before.outputs) == len(after.outputs) == 270
    assert (before.over(64), after.over(64)) == (0, 120)
    assert after.over(CAP - 1) == 0  # the cap never binds
    assert sum(before.inputs) == sum(after.inputs) == 40230
    assert before.refund_inputs == [193, 211, 227, 110]
    assert (before.final_words, after.final_words) == (8, 88)
    assert round(before.p99(), 2) == 59.68
    assert round(after.p99(), 2) == 251.68


def test_fs13_lab() -> None:
    before = fs13_lab.run("mock-a-fast")
    after = fs13_lab.run("mock-a-large")
    assert before.texts == after.texts  # every SLI sees the same
    assert before.per_answer == PER_ANSWER
    assert {
        j: v / 5 for j, v in after.per_answer.items()
    } == PER_ANSWER
    assert round(before.per_resolved, 7) == Decimal("0.0001601")
    assert round(after.per_resolved, 7) == Decimal("0.0008007")
    assert after.peak == Decimal("109.530")
