"""net_debt_incl_pensions: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

Apple meldet keinen Ausfinanzierungsstatus von Pensionen: 57.680 - 0 = 57.680 Mio. USD.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_net_debt_incl_pensions_hand_calculation() -> None:
    erg = rechne("net_debt_incl_pensions")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "pension_funded_status_nicht_gemeldet") == Decimal("0")
    assert erg.wert == Decimal("57680000000")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_net_debt_incl_pensions_failed_checkpoint_stops() -> None:
    erg = rechne("net_debt_incl_pensions", verschiedene_waehrung("cash"))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-01")


def test_net_debt_incl_pensions_missing_input_is_unknown() -> None:
    erg = rechne("net_debt_incl_pensions", ohne("cash"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "cash" in erg.grund
