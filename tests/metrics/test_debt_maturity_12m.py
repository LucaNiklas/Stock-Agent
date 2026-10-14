"""debt_maturity_12m: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

Fällig: 12.350 + 0 + 7.979 = 20.329; Deckung 35.934 + 0 = 35.934 (S. 31). 20.329 / 35.934 =
0,565732.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_debt_maturity_12m_hand_calculation() -> None:
    erg = rechne("debt_maturity_12m")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "faellig_12m") == Decimal("20329000000")
    assert schritt(erg, "deckung") == Decimal("35934000000")
    assert q(erg.wert) == Decimal("0.565732")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_debt_maturity_12m_failed_checkpoint_stops() -> None:
    erg = rechne("debt_maturity_12m", mit("cash", T25, Decimal(0)))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_debt_maturity_12m_missing_input_is_unknown() -> None:
    erg = rechne("debt_maturity_12m", ohne("cash"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "cash" in erg.grund
