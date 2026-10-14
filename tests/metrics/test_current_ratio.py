"""current_ratio: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

147.957 / 165.631 = 0,893293 (S. 31).
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_current_ratio_hand_calculation() -> None:
    erg = rechne("current_ratio")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert) == Decimal("0.893293")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_current_ratio_failed_checkpoint_stops() -> None:
    erg = rechne("current_ratio", mit("current_liabilities", T25, Decimal(0)))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_current_ratio_missing_input_is_unknown() -> None:
    erg = rechne("current_ratio", ohne("current_assets"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "current_assets" in erg.grund
