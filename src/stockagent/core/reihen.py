"""Jahresreihen der Eingangsgrößen einer Firma (Eingabe für Kennzahlen, Trends und Scores).

Reine Datenstruktur ohne I/O. Gebaut wird sie in `data/inputs.py` aus `pit_query`, also immer
zum Zeitpunkt `as_of` (HR-07). Jeder Wert ist eine `Eingabe` mit Quelle, Währung, Einheit,
Periode und Veröffentlichung (HR-12).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from stockagent.core.calc import Eingabe, EingabeFehlt


@dataclass(frozen=True)
class Split:
    """Split oder Zusammenlegung: Werte, die vor `wirksam_ab` veröffentlicht wurden, stehen noch
    auf alter Basis. Faktor 4 bei 4:1, 0,1 bei 1:10 (erkannt in DQ-08)."""

    wirksam_ab: datetime
    faktor: Decimal
    verhaeltnis: str


@dataclass(frozen=True)
class Reihen:
    subjekt: str
    stichtage: tuple[date, ...]  # Geschäftsjahresenden, neuestes zuerst
    werte: Mapping[str, Mapping[date, Eingabe]]
    splits: tuple[Split, ...] = field(default=())
    # Grund je Eingabe, die ganz fehlt (etwa: kein Kurs, weil Hinterlegungsschein)
    luecken: Mapping[str, str] = field(default_factory=dict)
    # Feste Angaben aus config/, die Kennzahlen brauchen (etwa Unterwährungen)
    parameter: Mapping[str, Any] = field(default_factory=dict)

    def hat(self, name: str, stichtag: date) -> bool:
        return stichtag in self.werte.get(name, {})

    def hole(self, name: str, stichtag: date) -> Eingabe:
        try:
            return self.werte[name][stichtag]
        except KeyError:
            grund = f"{name}: {self.luecken[name]}" if name in self.luecken else name
            raise EingabeFehlt(grund, stichtag.isoformat()) from None

    def vorjahr(self, stichtag: date, jahre: int = 1) -> date:
        """Stichtag `jahre` Geschäftsjahre früher. Fehlt er, fehlt die Eingabe."""
        try:
            i = self.stichtage.index(stichtag)
            return self.stichtage[i + jahre]
        except (ValueError, IndexError):
            raise EingabeFehlt(f"Geschäftsjahr {jahre} vor", stichtag.isoformat()) from None
