"""net_debt: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

Finanzschulden 90.678 + 7.979 = 98.657 (zweiter Weg 78.328 + 12.350 + 7.979 = 98.657), Leasing
12.490 + 1.230 = 13.720, minus Kasse 35.934 und Wertpapiere 18.763 = 57.680 Mio. USD (S. 31,
42).
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_net_debt_hand_calculation() -> None:
    erg = rechne("net_debt")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "finanzschulden_weg_a") == Decimal("98657000000")
    assert schritt(erg, "finanzschulden_weg_b") == Decimal("98657000000")
    assert schritt(erg, "leasing") == Decimal("13720000000")
    assert erg.wert == Decimal("57680000000")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_net_debt_failed_checkpoint_stops() -> None:
    erg = rechne("net_debt", mit("debt_noncurrent", T25, Decimal("70000000000")))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-04")


def test_net_debt_missing_input_is_unknown() -> None:
    erg = rechne("net_debt", ohne("cash"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "cash" in erg.grund
