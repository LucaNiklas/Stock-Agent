"""ev_sales: Handrechnung aus Apples 10-K und dem Schlusskurs bei Yahoo.

Quellen und Seiten in tests/metrics/apple.py.

Unternehmenswert 3.890.779.996.359,54 (siehe test_enterprise_value) / Umsatz 416.161 Mio.
(S. 29) = 9,3492.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401


def test_ev_sales_hand_calculation() -> None:
    erg = rechne("ev_sales")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert, 4) == Decimal("9.3492")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])
