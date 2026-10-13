"""Zeitpunktbezug (Point-in-Time, SPEC 7.5, HR-07).

Reine Funktionen ohne Datenbank. Ein Wert (Unternehmen, Konzept, Einheit, Periode) kann in
mehreren Einreichungen vorkommen: Jeder 10-K wiederholt die Vorjahre, ein Restatement ändert
sie. Zum Analysedatum `as_of` gilt die zuletzt veröffentlichte Fassung mit
`published_at <= as_of`. Ein Restatement wirkt damit erst ab seinem Veröffentlichungstag.
`store.pit_query(as_of=...)` nutzt diese Funktionen.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol


class Fassung(Protocol):
    @property
    def schluessel(self) -> Hashable: ...

    @property
    def published_at(self) -> datetime: ...

    @property
    def accession(self) -> str: ...

    @property
    def value(self) -> Decimal: ...


def _reihenfolge(f: Fassung) -> tuple[datetime, str]:
    return (f.published_at, f.accession)


def _rundungsstelle(v: Decimal) -> int:
    """Exponent der letzten von null verschiedenen Ziffer (96700000000 -> 8)."""
    exp = v.normalize().as_tuple().exponent
    return exp if isinstance(exp, int) else 0


def nur_rundung(a: Decimal, b: Decimal) -> bool:
    """Gleiche Zahl, nur unterschiedlich gerundet (SPEC 3.2 Nr. 7).

    Viele Berichte wiederholen Vorjahreswerte im Anhang gröber gerundet, etwa 96.662 Mio. im
    10-K und 96,7 Mrd. im folgenden 10-Q. Das ist kein Restatement. Gilt, wenn der gröbere Wert
    auf seiner Rundungsstelle mit dem genaueren übereinstimmt (Abstand höchstens eine halbe
    Einheit dieser Stelle) und mindestens drei gültige Ziffern hat. So bleibt die mögliche
    Rundungsabweichung unter 0,5 Prozent, und 1 Mrd. gegen 0,95 Mrd. gilt als echte Änderung.
    """
    if a == b:
        return False
    grob, fein = (a, b) if _rundungsstelle(a) > _rundungsstelle(b) else (b, a)
    stelle = _rundungsstelle(grob)
    if stelle <= 0 or stelle == _rundungsstelle(fein) or grob == 0:
        return False
    if len(grob.normalize().as_tuple().digits) < 3:
        return False
    return abs(grob - fein) * 2 <= Decimal(1).scaleb(stelle)


def _verlauf[F: Fassung](liste: list[F]) -> tuple[F, list[tuple[F, F]]]:
    """Fassungen eines Schlüssels in zeitlicher Folge zusammenführen.

    Gleicher Wert: die erste Veröffentlichung bleibt maßgeblich. Nur gerundet: die genauere
    Fassung bleibt oder ersetzt die gröbere. Anderer Wert: Restatement, die neue Fassung gilt
    ab ihrem Veröffentlichungstag.
    """
    liste = sorted(liste, key=_reihenfolge)
    aktuell = liste[0]
    aenderungen: list[tuple[F, F]] = []
    for f in liste[1:]:
        if f.value == aktuell.value:
            continue
        if nur_rundung(aktuell.value, f.value):
            if _rundungsstelle(f.value) < _rundungsstelle(aktuell.value):
                aktuell = f
            continue
        aenderungen.append((aktuell, f))
        aktuell = f
    return aktuell, aenderungen


def _gruppen[F: Fassung](fassungen: Iterable[F]) -> dict[Hashable, list[F]]:
    gruppen: dict[Hashable, list[F]] = defaultdict(list)
    for f in fassungen:
        gruppen[f.schluessel].append(f)
    return gruppen


def gueltig[F: Fassung](fassungen: Iterable[F], as_of: datetime) -> list[F]:
    """Je Schlüssel die zum Zeitpunkt `as_of` gültige Fassung.

    Werte nach `as_of` sind unsichtbar. Bei gleicher Veröffentlichungszeit gilt die höhere
    Accession-Nummer als spätere Einreichung.
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of ohne Zeitzone")
    sichtbar = (f for f in fassungen if f.published_at <= as_of)
    return [_verlauf(liste)[0] for liste in _gruppen(sichtbar).values()]


def erste[F: Fassung](fassungen: Iterable[F], as_of: datetime) -> list[F]:
    """Je Schlüssel die erste veröffentlichte Fassung, wie sie damals gemeldet wurde.

    Für Reihen, die spätere Berichte umrechnen (Aktienanzahl nach einem Split).
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of ohne Zeitzone")
    sichtbar = (f for f in fassungen if f.published_at <= as_of)
    return [min(liste, key=_reihenfolge) for liste in _gruppen(sichtbar).values()]


@dataclass(frozen=True)
class Aenderung:
    """Eine spätere Fassung meldet für denselben Schlüssel einen anderen Wert (SPEC 3.2 Nr. 7)."""

    alt: Fassung
    neu: Fassung


def restatements[F: Fassung](fassungen: Iterable[F]) -> list[Aenderung]:
    """Alle echten Wertänderungen je Schlüssel, ohne bloße Rundungsunterschiede."""
    return [
        Aenderung(alt, neu)
        for liste in _gruppen(fassungen).values()
        for alt, neu in _verlauf(liste)[1]
    ]
