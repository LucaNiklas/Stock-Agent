"""ebit_margin: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

Operating income 133.050 / Umsatz 416.161 (S. 29) = 0,319708.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from stockagent.core.reihen import Reihen
from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_ebit_margin_hand_calculation() -> None:
    erg = rechne("ebit_margin")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert) == Decimal("0.319708")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_ebit_margin_failed_checkpoint_stops() -> None:
    erg = rechne("ebit_margin", mit("revenue", T25, Decimal(-1)))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_ebit_margin_missing_input_is_unknown() -> None:
    erg = rechne("ebit_margin", ohne("ebit"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "ebit" in erg.grund


def test_ebit_margin_derived_when_operating_income_missing() -> None:
    """Wie Johnson & Johnson: kein operatives Ergebnis gemeldet. Vorsteuerergebnis 132.729
    (GuV Seite 29) plus gesetzter Zinsaufwand 1.000, geteilt durch Umsatz 416.161 (Mio. USD)."""
    reihen = ohne("ebit", reihen=mit_zinsen(Decimal("1000000000")))
    erg = rechne("ebit_margin", reihen)
    assert schritt(erg, "ebit_abgeleitet") == Decimal("133729000000")
    assert erg.wert is not None and q(erg.wert) == Decimal("0.321340")
    assert erg.vermerke and erg.vermerke[0].startswith("EBIT abgeleitet")


def test_ebit_margin_derived_from_net_interest() -> None:
    """Wie Nike: nur Zinsergebnis netto (hier gesetzt 50 Mio. Zinsertrag)."""
    w = {k: dict(v) for k, v in ohne("ebit").werte.items()}
    vorsteuer = w["pretax_income"][T25]
    w["interest_net"] = {T25: replace(vorsteuer, wert=Decimal("50000000"), quelle="Testwert")}
    erg = rechne("ebit_margin", Reihen(APPLE.subjekt, APPLE.stichtage, w, APPLE.splits))
    assert schritt(erg, "ebit_abgeleitet") == Decimal("132679000000")
    assert erg.wert is not None and q(erg.wert) == Decimal("0.318817")
    assert "Zinsergebnis netto" in erg.vermerke[0]
