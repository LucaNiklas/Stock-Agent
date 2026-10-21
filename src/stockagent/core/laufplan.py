"""Geschätzte Dauer eines Laufs für den Laufplan (SPEC 9.6, ADR 0014).

Keine Finanzgröße, aber Arithmetik, deshalb hier und über den Rechenweg (HR-06, HR-19):
Minuten = Bewertungen x Minuten je Bewertung + Tiefenanalysen x Minuten je Tiefenanalyse.
Prüfpunkt CP-02: Anzahlen und Minuten nicht negativ.
"""

from __future__ import annotations

from decimal import Decimal

from stockagent.core.calc import Ergebnis, Rechenweg, rechne


def dauer_minuten(
    bewertungen: int,
    tiefenanalysen: int,
    minuten_je_bewertung: Decimal,
    minuten_je_tiefenanalyse: Decimal,
) -> Ergebnis:
    r = Rechenweg("laufdauer", "1.0", "", "", pflicht=("CP-02",))

    def rechnung(rw: Rechenweg) -> Decimal:
        rw.pruefe(
            "CP-02",
            "Anzahlen und Minuten nicht negativ",
            min(bewertungen, tiefenanalysen) >= 0
            and min(minuten_je_bewertung, minuten_je_tiefenanalyse) >= 0,
        )
        b = rw.schritt(
            "bewerten",
            "anzahl * minuten",
            anzahl=Decimal(bewertungen),
            minuten=minuten_je_bewertung,
        )
        t = rw.schritt(
            "tiefenanalysen",
            "anzahl * minuten",
            anzahl=Decimal(tiefenanalysen),
            minuten=minuten_je_tiefenanalyse,
        )
        return rw.schritt("gesamt", "b + t", b=b, t=t)

    return rechne(r, rechnung)
