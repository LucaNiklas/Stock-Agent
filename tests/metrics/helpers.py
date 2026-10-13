"""Hilfen für Testfälle, die Apples Werte gezielt verändern."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from stockagent.core.calc import Eingabe
from stockagent.core.reihen import Reihen
from tests.metrics.apple import APPLE, T25


def verschiedene_waehrung(name: str = "capex") -> Reihen:
    """Ein Wert in EUR statt USD: CP-01 muss stoppen."""
    w = {k: dict(v) for k, v in APPLE.werte.items()}
    w[name][T25] = replace(w[name][T25], waehrung="EUR")
    return Reihen(APPLE.subjekt, APPLE.stichtage, w, APPLE.splits)


def mit_zinsen(betrag: Decimal) -> Reihen:
    """Apple meldet keinen Zinsaufwand. Für die Rechnung ein gesetzter Wert."""
    w = {k: dict(v) for k, v in APPLE.werte.items()}
    ebit = w["ebit"][T25]
    w["interest_expense"] = {
        T25: Eingabe(betrag, "Testwert", "monetary", T25, "USD", ebit.periode_start)
    }
    return Reihen(APPLE.subjekt, APPLE.stichtage, w, APPLE.splits)
