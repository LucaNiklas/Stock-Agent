"""Arithmetik des Goldstandards (SPEC 11.6, Bauschritt 10).

Goldwert eines Falls aus den im Fall genannten Eingaben und der genannten Formel, Fangquote je
Fehlerart und Übereinstimmung der Jury mit Luca (Cohens Kappa für zwei Klassen), alles über den
Rechenweg.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

from stockagent.core.calc import Ergebnis, Rechenweg, Stufe, rechne


def gold_wert(fall_id: str, formel: str, eingaben: Mapping[str, Decimal]) -> Ergebnis:
    r = Rechenweg("goldwert", "1.0", fall_id, "", pflicht=())
    return rechne(r, lambda rw: rw.schritt("goldwert", formel, **eingaben))


def quote(erkannt: int, gesamt: int) -> Decimal | None:
    """Anteil erkannter Fälle, None ohne Fälle."""
    if gesamt == 0:
        return None
    r = Rechenweg("fangquote", "1.0", "", "", pflicht=("CP-02",))

    def rechnung(rw: Rechenweg) -> Decimal:
        rw.pruefe("CP-02", "erkannt zwischen 0 und gesamt", 0 <= erkannt <= gesamt, Stufe.STOPP)
        return rw.schritt("quote", "erkannt / gesamt", erkannt=erkannt, gesamt=gesamt)

    return rechne(r, rechnung).wert


def kappa(paare: Sequence[tuple[bool, bool]]) -> Decimal | None:
    """Cohens Kappa zweier Urteiler mit Ja/Nein. None ohne Paare oder wenn die erwartete
    Übereinstimmung 1 ist (beide immer gleich und ohne Streuung, Kappa nicht definiert)."""
    if not paare:
        return None
    a = sum(1 for x, y in paare if x and y)
    b = sum(1 for x, y in paare if x and not y)
    c = sum(1 for x, y in paare if not x and y)
    d = sum(1 for x, y in paare if not x and not y)
    r = Rechenweg("cohens_kappa", "1.0", "", "", pflicht=())
    n = r.schritt("n", "a + b + c + d", a=a, b=b, c=c, d=d)
    po = r.schritt("beobachtet", "(a + d) / n", a=a, d=d, n=n)
    pe = r.schritt(
        "erwartet",
        "((a + b) / n) * ((a + c) / n) + ((c + d) / n) * ((b + d) / n)",
        a=a,
        b=b,
        c=c,
        d=d,
        n=n,
    )
    if pe == 1:
        return None
    return r.schritt("kappa", "(po - pe) / (1 - pe)", po=po, pe=pe)
