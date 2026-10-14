"""fcf: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

111.482 - 12.715 - 0 = 98.767 Mio. USD (S. 33).
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_fcf_hand_calculation() -> None:
    erg = rechne("fcf")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "capex_intangibles_nicht_gemeldet") == Decimal("0")
    assert erg.wert == Decimal("98767000000")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_fcf_failed_checkpoint_stops() -> None:
    erg = rechne("fcf", verschiedene_waehrung())
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-01")


def test_fcf_missing_input_is_unknown() -> None:
    erg = rechne("fcf", ohne("operating_cash_flow"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "operating_cash_flow" in erg.grund
