"""ev_ebit_normalized: Handrechnung für Apple 2025 mit 10 Geschäftsjahren EBIT.

EBIT in Mio. USD, 2025 bis 2020 aus den 10-K (S. 29), 2019 bis 2016 aus us-gaap:OperatingIncomeLoss
(Quellen in tests/metrics/apple.py): 133.050 + 123.216 + 114.301 + 119.437 + 108.949 + 66.288 +
63.930 + 70.898 + 61.344 + 60.024 = 921.437, Durchschnitt 92.143,7.
Unternehmenswert 3.890.779.996.359,54 / 92.143,7 Mio. = 42,2251.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, APPLE_10J, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401


def test_ev_ebit_normalized_hand_calculation() -> None:
    erg = rechne("ev_ebit_normalized", APPLE_10J)
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "ebit_durchschnitt") == Decimal("92143700000")
    assert q(erg.wert, 4) == Decimal("42.2251")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_ev_ebit_normalized_needs_seven_years() -> None:
    erg = rechne("ev_ebit_normalized")  # nur 2025 bis 2020: 6 Jahre
    assert erg.unknown and "mindestens 7" in str(erg.grund)
