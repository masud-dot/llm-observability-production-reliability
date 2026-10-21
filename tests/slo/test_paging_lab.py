"""The paging lab (Chapter 14): FS-02 and FS-03 must page, a
five-minute blip must not, and the worked numbers of Section 14.6."""

import re
from fractions import Fraction

import pytest

from wrenholt.labs import paging_lab as lab


@pytest.fixture(scope="module")
def outcomes() -> dict[str, lab.Outcome]:
    return {sc.name: lab.run(sc) for sc in lab.SCENARIOS}


def fired(o: lab.Outcome) -> list[int | None]:
    return [o.fired[k] for k in ("page 1h", "page 6h", "ticket 3d")]


def test_traffic() -> None:
    assert lab.ANSWERS * 60 == 120
    assert lab.INTERACTIVE * 60 == 90


def test_sustained_faults_page(
    outcomes: dict[str, lab.Outcome],
) -> None:
    outage = outcomes["FS-03, 30 minutes"]
    assert fired(outage) == [1, 3, 5]
    assert outage.at_page == Fraction(2, 1) / Fraction(8064, 100)
    assert round(float(outage.at_page), 4) == 0.0248
    assert round(float(outage.episode), 3) == 0.744  # 60 of 80.64
    brownout = outcomes["FS-02, 2 hours"]
    assert fired(brownout) == [9, 22, 44]
    assert round(float(brownout.at_page or 0), 4) == 0.0223
    assert round(float(brownout.episode), 4) == 0.2976  # 180/604.8


def test_a_five_minute_blip_does_not_page(
    outcomes: dict[str, lab.Outcome],
) -> None:
    blip = outcomes["FS-02, 5 minutes"]
    assert fired(blip) == [None, None, None]
    assert round(float(blip.episode), 4) == 0.0124  # 7.5 of 604.8
    assert blip.short_alone == 1  # the 5-minute window alone pages
    by = {sc.name: sc for sc in lab.SCENARIOS}
    peak = max(r[1] for r in lab.ratios(by["FS-02, 5 minutes"], 60))
    assert peak == 1 / 12  # 7.5 of 90: under 0.144
    # A five-minute outage is not a blip: 10 failures, 12.4 per cent.
    short_outage = outcomes["FS-03, 5 minutes"]
    assert fired(short_outage) == [1, 3, 5]
    assert round(float(short_outage.episode), 3) == 0.124
    assert short_outage.episode == 10 * blip.episode


def test_low_traffic(outcomes: dict[str, lab.Outcome]) -> None:
    by = {sc.name: sc for sc in lab.SCENARIOS}
    quiet = lab.Counts(by["one failure, 10/h"])
    assert quiet.window(1, 360)[1] == 60  # six hours hold 60
    one = outcomes["one failure, 10/h"]
    assert fired(one) == [None, None, 1]  # a ticket, no page
    assert round(float(one.episode), 4) == 0.1488  # 1 of 6.72
    outage = outcomes["FS-03 at 10/h, 2 h"]
    assert fired(outage) == [7, 7, 1]  # the second failure pages
    assert round(float(outage.at_page or 0), 3) == 0.298


def test_reset_times(outcomes: dict[str, lab.Outcome]) -> None:
    reset = outcomes["FS-03, 30 minutes"].reset
    assert reset == {"page 1h": 5, "page 6h": 30, "ticket 3d": 360}


def test_the_lab_prints_its_findings(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lab.main()
    out = capsys.readouterr().out
    assert re.search(r"FS-02, 5 minutes( +-){4} +1\.2%", out)
    assert "the 5-minute window alone pages on 6 of 6" in out
    assert "page 1h 5, page 6h 30, ticket 3d 360 min" in out
    assert max(len(line) for line in out.splitlines()) <= 70
