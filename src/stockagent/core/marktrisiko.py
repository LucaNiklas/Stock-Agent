"""Marktbezogene Risikoeingänge (SPEC 6.4): Volatilität, größter Kursrückgang, Illiquidität.

Kurse werden zuerst in EUR umgerechnet (Kurs / Referenzkurs je EUR, Unterwährungen vorher durch
100), dann Tagesrenditen gebildet. Reine Rechnung auf Listen, ohne I/O.

- Volatilität 3 Jahre: Standardabweichung der Tagesrenditen der letzten 756 Handelstage mal
  Wurzel aus 252 (annualisiert).
- Größter Kursrückgang 5 Jahre: größter Abstand vom laufenden Höchststand, als Anteil.
- Amihud-Illiquidität: Mittel über die letzten 250 Handelstage von |Tagesrendite| / Umsatz in EUR
  (Volumen mal Kurs in EUR).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from itertools import pairwise

HANDELSTAGE_JAHR = 252


@dataclass(frozen=True)
class Tag:
    datum: date
    kurs_eur: Decimal
    volumen: int | None


def in_eur(kurs: Decimal, je_eur: Decimal | None, teiler: int) -> Decimal:
    """Kurs in EUR. `je_eur` = Einheiten der Währung je EUR (None bei EUR), `teiler` 100 bei
    Unterwährungen wie GBp."""
    with localcontext() as ctx:
        ctx.prec = 28
        betrag = kurs / teiler
        return betrag if je_eur is None else betrag / je_eur


def _renditen(tage: Sequence[Tag]) -> list[Decimal]:
    with localcontext() as ctx:
        ctx.prec = 28
        return [b.kurs_eur / a.kurs_eur - 1 for a, b in pairwise(tage)]


def volatilitaet(tage: Sequence[Tag], jahre: int = 3) -> Decimal | None:
    letzte = list(tage)[-(HANDELSTAGE_JAHR * jahre + 1) :]
    r = _renditen(letzte)
    if len(r) < HANDELSTAGE_JAHR:
        return None
    with localcontext() as ctx:
        ctx.prec = 28
        mittel = sum(r, Decimal(0)) / len(r)
        varianz = sum(((x - mittel) ** 2 for x in r), Decimal(0)) / (len(r) - 1)
        return (varianz * HANDELSTAGE_JAHR).sqrt()


def drawdown(tage: Sequence[Tag], jahre: int = 5) -> Decimal | None:
    letzte = list(tage)[-(HANDELSTAGE_JAHR * jahre) :]
    if len(letzte) < HANDELSTAGE_JAHR:
        return None
    hoch, groesster = letzte[0].kurs_eur, Decimal(0)
    with localcontext() as ctx:
        ctx.prec = 28
        for t in letzte:
            hoch = max(hoch, t.kurs_eur)
            groesster = max(groesster, 1 - t.kurs_eur / hoch)
    return groesster


def amihud(tage: Sequence[Tag]) -> Decimal | None:
    letzte = list(tage)[-(HANDELSTAGE_JAHR + 1) :]
    werte = []
    with localcontext() as ctx:
        ctx.prec = 28
        for a, b in pairwise(letzte):
            if not b.volumen:
                continue
            umsatz = b.kurs_eur * b.volumen
            if umsatz > 0:
                werte.append(abs(b.kurs_eur / a.kurs_eur - 1) / umsatz)
        if len(werte) < HANDELSTAGE_JAHR // 2:
            return None
        return sum(werte, Decimal(0)) / len(werte)
