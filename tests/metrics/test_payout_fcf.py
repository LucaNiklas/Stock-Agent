"""payout_fcf: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

(15.421 + 90.711) / 98.767 = 1,074569 (S. 33).
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_payout_fcf_hand_calculation() -> None:
    erg = rechne("payout_fcf")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "ausschuettung") == Decimal("106132000000")
    assert q(erg.wert) == Decimal("1.074569")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_payout_fcf_failed_checkpoint_stops() -> None:
    erg = rechne("payout_fcf", mit("operating_cash_flow", T25, Decimal("12715000000")))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_payout_fcf_missing_input_is_unknown() -> None:
    erg = rechne("payout_fcf", ohne("capex"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "capex" in erg.grund
