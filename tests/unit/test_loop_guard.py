"""The loop guard (Chapter 9): what it stops, and FS-06 end to end."""

from wrenholt.gateway import ToolCall
from wrenholt.labs.fs06_lab import CapOnly, run
from wrenholt.orchestrator.guard import LoopGuard


def call(n: int, arguments: str) -> ToolCall:
    return ToolCall(f"call_{n}", "lookup_order", arguments)


def test_a_repeat_is_the_same_call_however_it_is_spelled() -> None:
    guard = LoopGuard()
    assert not guard.repeats(call(1, '{"order_id": "WG-100006"}'))
    # A new call ID, other spacing: still the same call.
    assert guard.repeats(call(2, '{"order_id":"WG-100006"}'))


def test_other_arguments_or_tools_are_not_repeats() -> None:
    guard = LoopGuard()
    assert not guard.repeats(call(1, '{"order_id": "WG-100006"}'))
    assert not guard.repeats(call(2, '{"order_id": "WG-100007"}'))
    same_args = '{"order_id": "WG-100006"}'
    other_tool = ToolCall("call_3", "issue_refund", same_args)
    assert not guard.repeats(other_tool)


def test_the_step_limit() -> None:
    guard = LoopGuard(max_steps=2)
    assert [guard.step() for _ in range(3)] == [True, True, False]


def test_fs06_cap_only_runs_to_the_cap() -> None:
    before = run(CapOnly)
    assert before.stop == "step_limit"
    assert (before.model_calls, before.tool_calls) == (26, 25)
    assert before.fingerprints == 1  # one call, made 25 times
    assert before.bucket == 'le="32"'


def test_fs06_the_guard_stops_the_first_repeat() -> None:
    after = run(LoopGuard)
    assert after.stop == "repeated_call"
    # Two decisions (the second repeats the first) and the answer.
    assert (after.model_calls, after.tool_calls) == (3, 1)
    assert after.bucket == 'le="1"'
    assert after.answer == run(CapOnly).answer
