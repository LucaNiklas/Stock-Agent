"""growth_gap und margin_of_safety: Apple 2025.

growth_gap = implizites Wachstum 0,154955 (siehe test_implied_growth) minus Umsatzwachstum 5 Jahre
(416.161 / 274.515)^(1/5) - 1 = 0,086774 (siehe test_revenue_cagr_5y) = 0,068181.
margin_of_safety = DCF Base 94,82 (siehe test_dcf_szenarien) / Kurs 255,46 - 1 = -0,6288.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import q, rechne, schritt


def test_growth_gap_hand_calculation() -> None:
    erg = rechne("growth_gap")
    assert erg.wert is not None, erg.grund
    assert q(schritt(erg, "cagr")) == Decimal("0.086774")
    assert q(erg.wert) == Decimal("0.068181")


def test_margin_of_safety_hand_calculation() -> None:
    erg = rechne("margin_of_safety")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert, 4) == Decimal("-0.6288")
