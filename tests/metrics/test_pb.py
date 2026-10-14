"""pb: Handrechnung aus Apples 10-K und dem Schlusskurs bei Yahoo.

Quellen und Seiten in tests/metrics/apple.py.

Börsenwert 3.833.099.996.359,54 (siehe test_market_cap) / Eigenkapital 73.733 Mio. (S. 31)
= 51,9862.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401


def test_pb_hand_calculation() -> None:
    erg = rechne("pb")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert, 4) == Decimal("51.9862")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_pb_negative_equity_is_not_defined() -> None:
    erg = rechne("pb", mit("equity", T25, Decimal("-5000000000")))
    assert erg.unknown and erg.ungereimtheit is None
