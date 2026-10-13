"""Chapter 10: what Wrenholt emits fits its cardinality budget.

The run records with the SDK's own MeterProvider, without the guard,
so a metric attribute outside its budget fails here before the guard
ever has to drop it in production.
"""

from wrenholt.telemetry import conventions as c

Emitted = tuple[set[str], list[tuple[str, str, str, set[str]]]]


def test_every_emitted_metric_fits_its_budget(
    emitted: Emitted,
) -> None:
    budgets = {b.metric: b for b in c.BUDGET}
    for name, _, _, keys in emitted[1]:
        assert keys <= set(budgets[name].attributes), name


def test_no_emitted_metric_carries_an_identifier(
    emitted: Emitted,
) -> None:
    identifiers = {
        c.RESPONSE_ID, c.TOOL_CALL_ID, c.TOOL_FINGERPRINT,
        c.CONTENT_REF, c.RETRIEVAL_DOCUMENTS,
    }  # fmt: skip
    for name, _, _, keys in emitted[1]:
        assert not keys & identifiers, name
