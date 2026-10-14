"""market_cap: Handrechnung aus Apples 10-K und dem Schlusskurs bei Yahoo.

Quellen und Seiten in tests/metrics/apple.py.

Schlusskurs 26.09.2025 (letzter Handelstag vor dem Geschäftsjahresende 27.09.2025)
255,4600067138672 USD mal 15.004.697 Tsd. verwässerte Aktien (S. 29)
= 3.833.099.996.359,54 USD, rund 3.833 Mrd. USD.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401


def test_market_cap_hand_calculation() -> None:
    erg = rechne("market_cap")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert, 2) == Decimal("3833099996359.54")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_market_cap_without_price_is_unknown_with_reason() -> None:
    erg = rechne("market_cap", ohne("kurs"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "kurs" in erg.grund


def test_market_cap_nonpositive_price_stops() -> None:
    erg = rechne("market_cap", mit("kurs", T25, Decimal(0)))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")
