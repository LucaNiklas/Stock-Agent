"""Prüfung von Wertpapierkennungen (reine Funktionen, SPEC 7.1)."""

from __future__ import annotations

import re

_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def isin_is_valid(isin: str) -> bool:
    """ISIN nach ISO 6166: Format und Prüfziffer (Luhn über die in Ziffern umgesetzten Zeichen)."""
    if not _ISIN.match(isin):
        return False
    digits = "".join(str(int(ch, 36)) for ch in isin[:-1])
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10 == int(isin[-1])


def change_exceeds(previous: int, current: int, max_pct: float) -> bool:
    """True, wenn sich eine Anzahl gegenüber dem Vorstand um mehr als max_pct Prozent ändert."""
    if previous == 0:
        return False
    return abs(current - previous) * 100 > max_pct * previous
