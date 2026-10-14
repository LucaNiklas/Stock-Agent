"""sbc_to_revenue: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

12.863 / 416.161 = 0,030909 (S. 29, 33).
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_sbc_to_revenue_hand_calculation() -> None:
    erg = rechne("sbc_to_revenue")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert) == Decimal("0.030909")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_sbc_to_revenue_failed_checkpoint_stops() -> None:
    erg = rechne("sbc_to_revenue", mit("revenue", T25, Decimal(-1)))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_sbc_to_revenue_not_meaningful_is_unknown_without_inconsistency() -> None:
    """Wirtschaftlich möglicher Fall (Verlust, negatives Eigenkapital, kein Umsatz):
    nicht aussagekräftig, kein Datenfehler."""
    erg = rechne("sbc_to_revenue", mit("revenue", T25, Decimal(0)))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and erg.grund.startswith("Nicht definiert")


def test_sbc_to_revenue_missing_input_is_unknown() -> None:
    erg = rechne("sbc_to_revenue", ohne("sbc"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "sbc" in erg.grund
