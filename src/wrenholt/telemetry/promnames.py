"""OTLP names as Prometheus stores them (Chapter 5).

Prometheus 3 translates OTLP with underscore escaping and suffixes:
dots become underscores, a unit becomes a suffix (s to _seconds),
counters gain _total, and histograms _bucket, _sum and _count.
Annotations in braces, such as {attempt}, add nothing. The tests
use the names a native run in Chapter 4 found in Prometheus.
"""

import re

UNIT_SUFFIX = {"s": "seconds", "ms": "milliseconds", "By": "bytes"}


def label(attribute: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", attribute)


def series(name: str, instrument: str, unit: str) -> set[str]:
    base = re.sub(r"[^A-Za-z0-9_:]", "_", name)
    suffix = UNIT_SUFFIX.get(unit, "")
    if suffix and not base.endswith(f"_{suffix}"):
        base = f"{base}_{suffix}"
    if instrument == "counter":
        return {f"{base}_total"}
    if instrument == "histogram":
        return {
            f"{base}_{part}" for part in ("bucket", "sum", "count")
        }
    return {base}
