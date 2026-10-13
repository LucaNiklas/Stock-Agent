"""sloan_accruals: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

(112.010 - 111.482) / 362.110,5 = 0,001458 (S. 29, 31, 33).
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_sloan_accruals_hand_calculation() -> None:
    erg = rechne("sloan_accruals")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "accruals") == Decimal("528000000")
    assert q(erg.wert) == Decimal("0.001458")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_sloan_accruals_failed_checkpoint_stops() -> None:
    erg = rechne("sloan_accruals", mit("total_assets", T25, Decimal("-724221000000")))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_sloan_accruals_missing_input_is_unknown() -> None:
    erg = rechne("sloan_accruals", ohne("operating_cash_flow"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "operating_cash_flow" in erg.grund
