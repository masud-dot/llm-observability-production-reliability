"""Error-budget arithmetic (Chapter 12).

An objective of 99.9 per cent leaves a budget of 0.1 per cent of the
valid events in the window. The burn rate is the error ratio over
that budget: at a burn rate of 1 the budget lasts exactly the
window. Decimal keeps every worked number in the chapter exact.
"""

from decimal import Decimal

WINDOW_HOURS = Decimal(28 * 24)  # the SLO file's 28d


def budget(objective: Decimal) -> Decimal:
    """The share of valid events allowed to be bad."""
    if not 0 < objective < 1:
        raise ValueError(f"objective out of range: {objective}")
    return 1 - objective


def allowed_bad(objective: Decimal, valid: int) -> Decimal:
    return budget(objective) * valid


def burn_rate(bad: int, valid: int, objective: Decimal) -> Decimal:
    """How fast the budget is being spent: the error ratio over the
    budget."""
    if valid == 0:
        raise ValueError("no valid events: no error ratio")
    return Decimal(bad) / valid / budget(objective)


def lasts_hours(
    burn: Decimal, window_hours: Decimal = WINDOW_HOURS
) -> Decimal:
    """How long a full budget lasts at this burn rate."""
    return window_hours / burn


def spent(
    burn: Decimal,
    hours: Decimal,
    window_hours: Decimal = WINDOW_HOURS,
) -> Decimal:
    """The share of the window's budget spent in `hours`."""
    return burn * hours / window_hours


def remaining(bad: int, valid: int, objective: Decimal) -> Decimal:
    """The share of the budget left; negative once overspent."""
    return 1 - burn_rate(bad, valid, objective)
