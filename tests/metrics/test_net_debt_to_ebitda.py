"""net_debt_to_ebitda: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

EBITDA = 133.050 + 11.698 = 144.748 (S. 29, 33). 57.680 / 144.748 = 0,398486.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_net_debt_to_ebitda_hand_calculation() -> None:
    erg = rechne("net_debt_to_ebitda")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "ebitda") == Decimal("144748000000")
    assert q(erg.wert) == Decimal("0.398486")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_net_debt_to_ebitda_failed_checkpoint_stops() -> None:
    erg = rechne("net_debt_to_ebitda", verschiedene_waehrung("cash"))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-01")


def test_net_debt_to_ebitda_not_meaningful_is_unknown_without_inconsistency() -> None:
    """Wirtschaftlich möglicher Fall (Verlust, negatives Eigenkapital, kein Umsatz):
    nicht aussagekräftig, kein Datenfehler."""
    erg = rechne("net_debt_to_ebitda", mit("ebit", T25, Decimal("-11698000000")))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and erg.grund.startswith("Nicht definiert")


def test_net_debt_to_ebitda_missing_input_is_unknown() -> None:
    erg = rechne("net_debt_to_ebitda", ohne("depreciation"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "depreciation" in erg.grund
