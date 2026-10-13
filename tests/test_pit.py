"""HR-07 und SPEC 7.5: gültige Fassung zum Analysedatum, Restatements erst ab ihrem Datum."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from stockagent.core import pit


@dataclass(frozen=True)
class F:
    schluessel: str
    published_at: datetime
    accession: str
    value: Decimal


def t(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, 20, 0, tzinfo=UTC)


ORIGINAL = F("umsatz@2023", t(2023, 11, 3), "0001-23-000001", Decimal(100))
WIEDERHOLT = F("umsatz@2023", t(2024, 11, 1), "0001-24-000001", Decimal(100))
RESTATED = F("umsatz@2023", t(2025, 2, 1), "0001-25-000002", Decimal(95))


def test_value_before_publication_is_invisible() -> None:
    assert pit.gueltig([ORIGINAL], t(2023, 11, 2)) == []


def test_restatement_only_from_its_date() -> None:
    alle = [RESTATED, ORIGINAL, WIEDERHOLT]
    assert pit.gueltig(alle, t(2024, 12, 31))[0].value == 100
    assert pit.gueltig(alle, t(2025, 2, 1))[0].value == 95


def test_same_time_later_accession_wins() -> None:
    a = F("k", t(2025, 1, 1), "0001-25-000001", Decimal(1))
    b = F("k", t(2025, 1, 1), "0001-25-000002", Decimal(2))
    assert pit.gueltig([b, a], t(2025, 1, 2))[0].value == 2


def test_restatements_found_only_on_value_change() -> None:
    aend = pit.restatements([RESTATED, WIEDERHOLT, ORIGINAL])
    assert len(aend) == 1
    # Bei gleichem Wert bleibt die erste Veröffentlichung maßgeblich
    assert aend[0].alt == ORIGINAL and aend[0].neu == RESTATED


def test_as_of_needs_timezone() -> None:
    with pytest.raises(ValueError):
        pit.gueltig([ORIGINAL], datetime(2025, 1, 1))


@pytest.mark.parametrize(
    ("a", "b", "rundung"),
    [
        ("96662000000", "96700000000", True),  # 10-K genau, 10-Q in Mrd. gerundet
        ("105103000000", "105100000000", True),
        ("96662000000", "96800000000", False),  # 96,8 Mrd. ist keine Rundung von 96,662
        ("950000000", "1000000000", False),  # eine gültige Ziffer: echte Änderung
        ("100", "95", False),
        ("12.34", "12.34", False),  # gleich ist keine Rundung
    ],
)
def test_rounding_is_not_a_restatement(a: str, b: str, rundung: bool) -> None:
    assert pit.nur_rundung(Decimal(a), Decimal(b)) is rundung
    assert pit.nur_rundung(Decimal(b), Decimal(a)) is rundung


def test_precise_version_wins_over_rounded_repeat() -> None:
    genau = F("k", t(2024, 11, 1), "0001-24-000123", Decimal("96662000000"))
    gerundet = F("k", t(2025, 1, 31), "0001-25-000008", Decimal("96700000000"))
    assert pit.gueltig([genau, gerundet], t(2025, 6, 1)) == [genau]
    assert pit.restatements([genau, gerundet]) == []
    # Erst gerundet, dann genau: die genaue Fassung übernimmt
    spaeter = F("k", t(2025, 10, 31), "0001-25-000079", Decimal("96662000000"))
    assert pit.gueltig([gerundet, spaeter], t(2025, 11, 1)) == [spaeter]


def test_first_version_as_reported() -> None:
    alle = [RESTATED, ORIGINAL, WIEDERHOLT]
    assert pit.erste(alle, t(2025, 6, 1)) == [ORIGINAL]
