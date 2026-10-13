"""quick_ratio: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

(147.957 - 5.718) / 165.631 = 0,858770 (S. 31).
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_quick_ratio_hand_calculation() -> None:
    erg = rechne("quick_ratio")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "ohne_vorraete") == Decimal("142239000000")
    assert q(erg.wert) == Decimal("0.858770")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_quick_ratio_failed_checkpoint_stops() -> None:
    erg = rechne("quick_ratio", mit("current_liabilities", T25, Decimal(0)))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_quick_ratio_missing_input_is_unknown() -> None:
    erg = rechne("quick_ratio", ohne("current_liabilities"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "current_liabilities" in erg.grund
