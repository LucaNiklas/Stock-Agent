"""revenue_cagr_5y: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

(416.161 / 274.515) ^ (1/5) - 1 = 0,086774 (10-K 2025 S. 29, 10-K 2022 S. 29).
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_revenue_cagr_5y_hand_calculation() -> None:
    erg = rechne("revenue_cagr_5y")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert) == Decimal("0.086774")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_revenue_cagr_5y_failed_checkpoint_stops() -> None:
    erg = rechne("revenue_cagr_5y", mit("revenue", T20, Decimal(-1)))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_revenue_cagr_5y_zero_start_is_not_defined() -> None:
    """Kein Umsatz vor 5 Jahren (etwa Gründung): Wachstumsrate nicht definiert."""
    erg = rechne("revenue_cagr_5y", mit("revenue", T20, Decimal(0)))
    assert erg.unknown and erg.ungereimtheit is None


def test_revenue_cagr_5y_missing_input_is_unknown() -> None:
    erg = rechne("revenue_cagr_5y", ohne("revenue"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "revenue" in erg.grund
