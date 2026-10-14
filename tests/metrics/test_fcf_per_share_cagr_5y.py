"""fcf_per_share_cagr_5y: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

FCF 2020 = 80.674 - 7.309 = 73.365, je Aktie 73.365 / 17.528.214 Tsd. = 4,185529; 2025: 98.767 /
15.004.697 Tsd. = 6,582406. (6,582406 / 4,185529) ^ (1/5) - 1 = 0,094780.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_fcf_per_share_cagr_5y_hand_calculation() -> None:
    erg = rechne("fcf_per_share_cagr_5y")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert) == Decimal("0.094780")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_fcf_per_share_cagr_5y_failed_checkpoint_stops() -> None:
    erg = rechne("fcf_per_share_cagr_5y", mit("shares_diluted", T20, Decimal(0)))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_fcf_per_share_cagr_5y_negative_fcf_is_not_defined() -> None:
    erg = rechne("fcf_per_share_cagr_5y", mit("operating_cash_flow", T20, Decimal(0)))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and erg.grund.startswith("Nicht definiert")


def test_fcf_per_share_cagr_5y_missing_input_is_unknown() -> None:
    erg = rechne("fcf_per_share_cagr_5y", ohne("shares_diluted"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "shares_diluted" in erg.grund
