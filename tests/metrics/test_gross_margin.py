"""gross_margin: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

Bruttoergebnis 195.201 (S. 29) / Umsatz 416.161 (S. 29) = 0,469052. Zweiter Weg: Umsatz -
Umsatzkosten 220.960 = 195.201 (CP-04 bestanden).
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_gross_margin_hand_calculation() -> None:
    erg = rechne("gross_margin")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "brutto_aus_teilen") == Decimal("195201000000")
    assert schritt(erg, "bruttoergebnis") == Decimal("195201000000")
    assert q(erg.wert) == Decimal("0.469052")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_gross_margin_failed_checkpoint_stops() -> None:
    # Nur gemeldetes Bruttoergebnis, größer als der Umsatz: Marge über 100 %
    zu_hoch = mit("gross_profit", T25, Decimal("500000000000"), ohne("cost_of_revenue"))
    erg = rechne("gross_margin", zu_hoch)
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_gross_margin_missing_input_is_unknown() -> None:
    erg = rechne("gross_margin", ohne("revenue"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "revenue" in erg.grund


def test_gross_margin_second_way_disagrees() -> None:
    """Gemeldetes Bruttoergebnis passt nicht zu Umsatz minus Umsatzkosten: CP-04 stoppt."""
    erg = rechne("gross_margin", mit("gross_profit", T25, Decimal("200000000000")))
    assert erg.unknown and erg.grund is not None and erg.grund.startswith("CP-04")


def test_gross_margin_from_parts_when_not_reported() -> None:
    erg = rechne("gross_margin", ohne("gross_profit"))
    assert erg.wert is not None and q(erg.wert) == Decimal("0.469052")
