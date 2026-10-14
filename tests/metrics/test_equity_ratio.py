"""equity_ratio: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

73.733 / 359.241 = 0,205247 (S. 31).
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_equity_ratio_hand_calculation() -> None:
    erg = rechne("equity_ratio")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert) == Decimal("0.205247")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_equity_ratio_failed_checkpoint_stops() -> None:
    erg = rechne("equity_ratio", mit("equity", T25, Decimal("400000000000")))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_equity_ratio_missing_input_is_unknown() -> None:
    erg = rechne("equity_ratio", ohne("equity"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "equity" in erg.grund
