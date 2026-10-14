"""acquisition_intensity: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

Übernahmen 2021 bis 2025: 33 + 306 + 0 + 0 + 0 = 339; operativer Cashflow 104.038 + 122.151 +
110.543 + 118.254 + 111.482 = 566.468 (10-K 2025 und 2022, S. 33). 339 / 566.468 = 0,000598.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_acquisition_intensity_hand_calculation() -> None:
    erg = rechne("acquisition_intensity")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "uebernahmen_5j") == Decimal("339000000")
    assert schritt(erg, "ocf_5j") == Decimal("566468000000")
    assert q(erg.wert) == Decimal("0.000598")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_acquisition_intensity_failed_checkpoint_stops() -> None:
    erg = rechne("acquisition_intensity", verschiedene_waehrung("operating_cash_flow"))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-01")


def test_acquisition_intensity_not_meaningful_is_unknown_without_inconsistency() -> None:
    """Wirtschaftlich möglicher Fall (Verlust, negatives Eigenkapital, kein Umsatz):
    nicht aussagekräftig, kein Datenfehler."""
    erg = rechne("acquisition_intensity", mit("operating_cash_flow", T21, Decimal("-566468000000")))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and erg.grund.startswith("Nicht definiert")


def test_acquisition_intensity_missing_input_is_unknown() -> None:
    erg = rechne("acquisition_intensity", ohne("operating_cash_flow"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "operating_cash_flow" in erg.grund
