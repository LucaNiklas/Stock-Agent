"""dupont: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

Nettomarge 112.010 / 416.161 = 0,269151, Umschlag 416.161 / 362.110,5 = 1,149266, Hebel
362.110,5 / 65.341,5 = 5,541736. Produkt 1,714224.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_dupont_hand_calculation() -> None:
    erg = rechne("dupont")
    assert erg.wert is not None, erg.grund
    assert q(schritt(erg, "nettomarge")) == Decimal("0.269151")
    assert q(erg.wert) == Decimal("1.714224")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_dupont_failed_checkpoint_stops() -> None:
    erg = rechne("dupont", mit("equity", T25, Decimal(-1)))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_dupont_missing_input_is_unknown() -> None:
    erg = rechne("dupont", ohne("revenue"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "revenue" in erg.grund
