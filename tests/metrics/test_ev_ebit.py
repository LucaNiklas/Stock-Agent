"""ev_ebit: Handrechnung aus Apples 10-K und dem Schlusskurs bei Yahoo.

Quellen und Seiten in tests/metrics/apple.py.

Unternehmenswert 3.890.779.996.359,54 (siehe test_enterprise_value) / EBIT 133.050 Mio.
(S. 29) = 29,2430.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401


def test_ev_ebit_hand_calculation() -> None:
    erg = rechne("ev_ebit")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert, 4) == Decimal("29.2430")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_ev_ebit_negative_ebit_is_not_defined() -> None:
    erg = rechne("ev_ebit", mit("ebit", T25, Decimal("-1000000000")))
    assert erg.unknown and erg.ungereimtheit is None
