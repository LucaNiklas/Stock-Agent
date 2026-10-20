"""Vergleich der blinden Nachrechnung J1 mit dem gespeicherten Wert (SPEC 11.2 Ebene 1).

Relative Abweichung |J1 - gespeichert| / |gespeichert|: bis `match` Übereinstimmung, bis
`rundung` Rundung (Warnung), darüber `mismatch`. Bei gespeichertem Wert 0 zählt nur Gleichheit.
"""

from __future__ import annotations

from decimal import Decimal

from stockagent.core.calc import Rechenweg


def vergleich(j1: Decimal, gespeichert: Decimal, match: Decimal, rundung: Decimal) -> str:
    if gespeichert == 0:
        return "match" if j1 == 0 else "mismatch"
    r = Rechenweg("j1_vergleich", "1.0", "", "", pflicht=())
    abw = r.schritt("abweichung", "abs(j1 - soll) / abs(soll)", j1=j1, soll=gespeichert)
    if abw <= match:
        return "match"
    return "rounding" if abw <= rundung else "mismatch"
