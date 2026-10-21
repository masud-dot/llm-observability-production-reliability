"""Timer arithmetic for streams, and buckets that fit the SLI."""

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from wrenholt.gateway.streaming import StreamClock
from wrenholt.labs.fs02_lab import within
from wrenholt.slo.catalog import load_catalog
from wrenholt.telemetry import conventions as c


def test_first_chunk_then_gaps() -> None:
    clock = StreamClock(started=10.0)
    assert clock.chunk(10.4) is None  # the first chunk
    assert clock.chunk(10.52) == pytest.approx(0.12)
    assert clock.chunk(10.64) == pytest.approx(0.12)
    assert clock.to_first == pytest.approx(0.4)
    assert clock.chunks == 3
    assert clock.total(11.0) == pytest.approx(1.0)


def test_no_chunk_means_no_first_chunk() -> None:
    clock = StreamClock(started=0.0)
    assert (clock.to_first, clock.chunks) == (None, 0)


def test_ttfc_buckets_hold_every_sli_threshold() -> None:
    (ttfc,) = [s for s in load_catalog().slis if s.id == "ttfc"]
    thresholds = set(ttfc.thresholds_s.values())
    assert thresholds == set(c.SLI_THRESHOLDS)
    assert thresholds <= set(c.TTFC_BUCKETS)
    assert set(c.CHUNK_BUCKETS) <= set(c.TTFC_BUCKETS)
    assert not thresholds & set(c.CHUNK_BUCKETS)  # why they are added


def test_good_events_are_read_from_one_bucket() -> None:
    reader = InMemoryMetricReader()
    meter = MeterProvider(metric_readers=[reader]).get_meter("test")
    ttfc = meter.create_histogram(
        c.TIME_TO_FIRST_CHUNK,
        unit="s",
        explicit_bucket_boundaries_advisory=c.TTFC_BUCKETS,
    )
    for wait in (0.4, 2.4, 2.5, 2.6, 3.9, 4.1):
        ttfc.record(wait)
    assert within(reader, c.TIME_TO_FIRST_CHUNK, 2.5) == 3
    assert within(reader, c.TIME_TO_FIRST_CHUNK, 4.0) == 5
