"""ebit_margin: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

Operating income 133.050 / Umsatz 416.161 (S. 29) = 0,319708.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_ebit_margin_hand_calculation() -> None:
    erg = rechne("ebit_margin")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert) == Decimal("0.319708")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_ebit_margin_failed_checkpoint_stops() -> None:
    erg = rechne("ebit_margin", mit("revenue", T25, Decimal(-1)))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_ebit_margin_missing_input_is_unknown() -> None:
    erg = rechne("ebit_margin", ohne("ebit"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "ebit" in erg.grund
