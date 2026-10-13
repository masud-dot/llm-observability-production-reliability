"""The real Collector under the Chapter 10 labs, asserted.

Both labs run the pinned otelcol-contrib 0.162.0, so these tests
skip when it has not been fetched (scripts/fetch_collector.sh). The
FS-15 report is deterministic: seeded trace IDs, and a probabilistic
policy that hashes them. The overload counts were the same on every
run; how long the SDK waited is timing, so only its shape is checked.
"""

import pytest

from wrenholt.labs import fs15_lab, overload_lab
from wrenholt.labs.collector import binary

pytestmark = pytest.mark.skipif(
    binary() is None, reason="run scripts/fetch_collector.sh"
)

FS15 = [
    "FS-15: quiet failures under tail sampling (SIMULATED)",
    "24 answers, one at a time, through otelcol-contrib 0.162.0",
    "                       metrics  traces kept:    traces kept:",
    "                       show     errors and 5%   Wrenholt",
    "retried after a 429    5        5 of 5          5 of 5",
    "first chunk after 3 s  4        1 of 4          4 of 4",
    "substituted model      4        0 of 4          4 of 4",
    "nothing wrong          -        0 of 11         2 of 11",
    "traces each of Wrenholt's policies voted to keep:",
    "  errors 5, slow-first-chunk 4, model-mismatch 4, baseline 4",
]


def test_fs15_the_incident_policies_miss_the_quiet_failures() -> None:
    before = fs15_lab.run(fs15_lab.INCIDENT)
    after = fs15_lab.run(fs15_lab.wrenholt())
    assert fs15_lab.report(before, after) == FS15


def test_overload_is_accepted_then_dropped() -> None:
    spans = overload_lab.burst()
    results = [
        overload_lab.run(batch, queue, spans)
        for batch, queue in overload_lab.CASES
    ]
    batch_small, batch_large, no_batch = results
    # With the batch processor the receiver answers at once: the
    # SDK sees no failure, and a small queue drops what it cannot
    # take.
    assert (batch_small.failed, batch_small.refused) == (0, 0)
    assert (batch_small.rejected, batch_small.stored) == (1700, 300)
    assert (batch_large.rejected, batch_large.stored) == (0, 2000)
    # Without it the receiver refuses, the SDK retries, and nothing
    # is lost.
    assert (no_batch.failed, no_batch.stored) == (0, 2000)
    assert no_batch.refused == no_batch.rejected == 600
    assert max(batch_small.seconds, batch_large.seconds) < 1.0
    assert no_batch.seconds > 2.0  # the retries' backoff
