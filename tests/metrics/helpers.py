"""Hilfen für Testfälle, die Apples Werte gezielt verändern."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from stockagent.core.calc import Eingabe
from stockagent.core.reihen import Reihen
from tests.metrics.apple import APPLE, T25


def verschiedene_waehrung(name: str = "capex", t: date = T25, reihen: Reihen = APPLE) -> Reihen:
    """Ein Wert in EUR statt USD: CP-01 muss stoppen."""
    w = {k: dict(v) for k, v in reihen.werte.items()}
    w[name][t] = replace(w[name][t], waehrung="EUR")
    return replace(reihen, werte=w)


def mit_zinsen(betrag: Decimal) -> Reihen:
    """Apple meldet keinen Zinsaufwand. Für die Rechnung ein gesetzter Wert."""
    w = {k: dict(v) for k, v in APPLE.werte.items()}
    ebit = w["ebit"][T25]
    w["interest_expense"] = {
        T25: Eingabe(betrag, "Testwert", "monetary", T25, "USD", ebit.periode_start)
    }
    return replace(APPLE, werte=w)


def ohne_dividende_mit_yahoo(anzahl: int | None, t: date = T25) -> Reihen:
    """Bericht ohne Dividendenzahlung, dazu die Zahl der Dividenden bei Yahoo im Geschäftsjahr
    (None: Yahoo deckt das Jahr nicht ab)."""
    w = {k: dict(v) for k, v in APPLE.werte.items() if k != "dividends_paid"}
    if anzahl is not None:
        w["dividenden_yahoo"] = {
            t: Eingabe(Decimal(anzahl), "Yahoo AAPL Dividendenereignisse (Test)", "anzahl", t)
        }
    return replace(APPLE, werte=w)
