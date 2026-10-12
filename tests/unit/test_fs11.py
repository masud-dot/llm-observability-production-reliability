"""FS-11: a silent model change, caught by the pin."""

from wrenholt.labs.fs11_lab import differences, run


def test_the_pin_catches_what_the_answer_hides() -> None:
    before, after = run()
    assert after.text == before.text  # the customer sees no change
    assert (before.mismatch, before.mismatches) == (False, 0)
    assert (after.mismatch, after.mismatches) == (True, 1)
    assert after.response_model == "mock-a-fast-2026-10"
    assert differences(before.bundle, after.bundle) == [
        "response_model"
    ]
