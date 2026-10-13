"""fcf_margin: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

FCF = 111.482 - 12.715 = 98.767 (S. 33), / Umsatz 416.161 = 0,237329. Keine Zahlungen für
immaterielle Werte gemeldet: 0.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_fcf_margin_hand_calculation() -> None:
    erg = rechne("fcf_margin")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "fcf") == Decimal("98767000000")
    assert q(erg.wert) == Decimal("0.237329")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_fcf_margin_failed_checkpoint_stops() -> None:
    erg = rechne("fcf_margin", mit("revenue", T25, Decimal(0)))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_fcf_margin_missing_input_is_unknown() -> None:
    erg = rechne("fcf_margin", ohne("capex"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "capex" in erg.grund
