"""roe: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

Eigenkapital (73.733 + 56.950) / 2 = 65.341,5 (S. 31). 112.010 / 65.341,5 = 1,714224. DuPont:
0,269151 * 1,149266 * 5,541736 = 1,714224 (CP-04).
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_roe_hand_calculation() -> None:
    erg = rechne("roe")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "equity_durchschnitt") == Decimal("65341500000")
    assert schritt(erg, "total_assets_durchschnitt") == Decimal("362110500000")
    assert q(erg.wert) == Decimal("1.714224")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_roe_failed_checkpoint_stops() -> None:
    erg = rechne("roe", mit("equity", T24, Decimal(-1)))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_roe_missing_input_is_unknown() -> None:
    erg = rechne("roe", ohne("equity"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "equity" in erg.grund
