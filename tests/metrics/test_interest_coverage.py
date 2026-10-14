"""interest_coverage: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

Apple meldet seit 2023 keinen Zinsaufwand gesondert. Ohne Eingabe unknown. Fall mit Zinsaufwand
1.000: 133.050 / 1.000 = 133,05.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung


def test_interest_coverage_hand_calculation() -> None:
    erg = rechne("interest_coverage", mit_zinsen(Decimal(1000000000)))
    assert erg.wert == Decimal("133.05")


def test_interest_coverage_failed_checkpoint_stops() -> None:
    erg = rechne(
        "interest_coverage", verschiedene_waehrung("ebit", reihen=mit_zinsen(Decimal(1000)))
    )
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-01")


def test_interest_coverage_not_meaningful_is_unknown_without_inconsistency() -> None:
    """Wirtschaftlich möglicher Fall (Verlust, negatives Eigenkapital, kein Umsatz):
    nicht aussagekräftig, kein Datenfehler."""
    erg = rechne("interest_coverage", mit_zinsen(Decimal(0)))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and erg.grund.startswith("Nicht definiert")


def test_interest_coverage_missing_input_is_unknown() -> None:
    erg = rechne("interest_coverage", ohne("interest_expense"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "interest_expense" in erg.grund
