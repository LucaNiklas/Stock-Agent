"""buyback_yield: Handrechnung aus Apples 10-K und dem Schlusskurs bei Yahoo.

Quellen und Seiten in tests/metrics/apple.py.

Rückkäufe 90.711 Mio. (S. 33) minus Ausgabe neuer Aktien (Apple meldet keine eigene Zeile, 0)
/ Börsenwert 3.833.099.996.359,54 (siehe test_market_cap) = 0,023665, also 2,37 %.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401


def test_buyback_yield_hand_calculation() -> None:
    erg = rechne("buyback_yield")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "netto_rueckkauf") == Decimal("90711000000")
    assert q(erg.wert) == Decimal("0.023665")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])
