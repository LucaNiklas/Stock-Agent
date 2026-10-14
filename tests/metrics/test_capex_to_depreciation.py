"""capex_to_depreciation: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

12.715 / 11.698 = 1,086938 (S. 33).
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_capex_to_depreciation_hand_calculation() -> None:
    erg = rechne("capex_to_depreciation")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert) == Decimal("1.086938")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_capex_to_depreciation_failed_checkpoint_stops() -> None:
    erg = rechne("capex_to_depreciation", mit("depreciation", T25, Decimal(0)))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_capex_to_depreciation_missing_input_is_unknown() -> None:
    erg = rechne("capex_to_depreciation", ohne("depreciation"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "depreciation" in erg.grund
