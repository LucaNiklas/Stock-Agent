"""shareholder_yield: Handrechnung aus Apples 10-K und dem Schlusskurs bei Yahoo.

Quellen und Seiten in tests/metrics/apple.py.

Nettoverschuldung 2024: Finanzschulden 96.662 + 9.967 = 106.629, Leasing 11.534 + 896 = 12.430,
minus Kasse 29.943 und Wertpapiere 35.228 = 53.888 Mio. (S. 31, 42). 2025: 57.680 Mio.
(siehe test_net_debt). Schuldenabbau 53.888 - 57.680 = -3.792 Mio. (Apple hat netto mehr
Schulden).
An Kapitalgeber: Dividenden 15.421 + Rückkäufe 90.711 - 3.792 = 102.340 Mio. / Börsenwert
3.833.099.996.359,54 = 0,026699, also 2,67 %.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401


def test_shareholder_yield_hand_calculation() -> None:
    erg = rechne("shareholder_yield")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "an_kapitalgeber") == Decimal("102340000000")
    assert q(erg.wert) == Decimal("0.026699")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_shareholder_yield_needs_prior_year() -> None:
    erg = rechne("shareholder_yield", ohne("cash", T24))
    assert erg.unknown and erg.ungereimtheit is None
