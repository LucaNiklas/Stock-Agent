"""ocf_to_net_income: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

111.482 / 112.010 = 0,995286 (S. 29, 33).
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_ocf_to_net_income_hand_calculation() -> None:
    erg = rechne("ocf_to_net_income")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert) == Decimal("0.995286")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_ocf_to_net_income_failed_checkpoint_stops() -> None:
    erg = rechne("ocf_to_net_income", mit("net_income", T25, Decimal(0)))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_ocf_to_net_income_missing_input_is_unknown() -> None:
    erg = rechne("ocf_to_net_income", ohne("operating_cash_flow"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "operating_cash_flow" in erg.grund
