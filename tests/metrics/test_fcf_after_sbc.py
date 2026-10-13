"""fcf_after_sbc: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

98.767 - 12.863 = 85.904 Mio. USD (S. 33).
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_fcf_after_sbc_hand_calculation() -> None:
    erg = rechne("fcf_after_sbc")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "fcf") == Decimal("98767000000")
    assert erg.wert == Decimal("85904000000")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_fcf_after_sbc_failed_checkpoint_stops() -> None:
    erg = rechne("fcf_after_sbc", verschiedene_waehrung("sbc"))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-01")


def test_fcf_after_sbc_missing_input_is_unknown() -> None:
    erg = rechne("fcf_after_sbc", ohne("sbc"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "sbc" in erg.grund
