"""roa: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

Bilanzsumme (359.241 + 364.980) / 2 = 362.110,5 (S. 31). 112.010 / 362.110,5 = 0,309325.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_roa_hand_calculation() -> None:
    erg = rechne("roa")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "total_assets_durchschnitt") == Decimal("362110500000")
    assert q(erg.wert) == Decimal("0.309325")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_roa_failed_checkpoint_stops() -> None:
    erg = rechne("roa", mit("total_assets", T25, Decimal("-724221000000")))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_roa_missing_input_is_unknown() -> None:
    erg = rechne("roa", ohne("net_income"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "net_income" in erg.grund
