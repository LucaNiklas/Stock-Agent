"""dividend_yield: Handrechnung aus Apples 10-K und dem Schlusskurs bei Yahoo.

Quellen und Seiten in tests/metrics/apple.py.

Gezahlte Dividenden 15.421 Mio. (S. 33) / Börsenwert 3.833.099.996.359,54
(siehe test_market_cap) = 0,004023, also 0,40 %.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401


def test_dividend_yield_hand_calculation() -> None:
    erg = rechne("dividend_yield")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert) == Decimal("0.004023")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_dividend_yield_negative_dividends_stop() -> None:
    erg = rechne("dividend_yield", mit("dividends_paid", T25, Decimal("-1")))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
