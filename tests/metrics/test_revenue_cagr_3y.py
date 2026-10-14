"""revenue_cagr_3y: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

(416.161 / 394.328) ^ (1/3) - 1 = 0,018125 (10-K 2025 S. 29, 10-K 2024 S. 29).
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_revenue_cagr_3y_hand_calculation() -> None:
    erg = rechne("revenue_cagr_3y")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert) == Decimal("0.018125")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_revenue_cagr_3y_failed_checkpoint_stops() -> None:
    erg = rechne("revenue_cagr_3y", mit("revenue", T22, Decimal(-1)))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_revenue_cagr_3y_missing_input_is_unknown() -> None:
    erg = rechne("revenue_cagr_3y", ohne("revenue"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "revenue" in erg.grund


def test_revenue_cagr_3y_shrinking_revenue_is_negative_growth() -> None:
    """Schrumpfender Umsatz ist ein normaler Fall: (300.000 / 394.328) ^ (1/3) - 1 = -0,0871"""
    erg = rechne("revenue_cagr_3y", mit("revenue", T25, Decimal("300000000000")))
    assert erg.wert is not None and q(erg.wert) == Decimal("-0.087104")
    assert erg.ungereimtheit is None and erg.grund is None
