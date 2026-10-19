"""fcf_yield: Handrechnung aus Apples 10-K und dem Schlusskurs bei Yahoo.

Quellen und Seiten in tests/metrics/apple.py.

Freier Cashflow 111.482 - 12.715 = 98.767 Mio. (S. 33) / Börsenwert 3.833.099.996.359,54
(siehe test_market_cap) = 0,025767, also 2,58 %.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401


def test_fcf_yield_hand_calculation() -> None:
    erg = rechne("fcf_yield")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "fcf") == Decimal("98767000000")
    assert q(erg.wert) == Decimal("0.025767")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])
