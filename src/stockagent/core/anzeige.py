"""Rundung und Formatierung für die Anzeige (SPEC 12.7: gerundet wird erst bei der Anzeige).

Liegt in `core/`, weil Prozent und Millionen eine Rechnung sind (HR-06). Gespeichert werden immer
die ungerundeten Werte.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal


def _gruppiert(x: Decimal, stellen: int) -> str:
    text = f"{x:,.{stellen}f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def formatiere(
    wert: Decimal | None, anzeige: str, stellen: int, waehrung: str | None = None
) -> str:
    """Deutsche Schreibweise. `anzeige` aus `rundung.anzeige` in config/metrics.yaml."""
    if wert is None:
        return "unbekannt"
    if anzeige in ("percent", "punkte"):
        x = (wert * 100).quantize(Decimal(1).scaleb(-stellen), ROUND_HALF_EVEN)
        zeichen = "+" if anzeige == "punkte" and x > 0 else ""
        return f"{zeichen}{_gruppiert(x, stellen)} {'%' if anzeige == 'percent' else 'Pkt.'}"
    if anzeige == "betrag":
        mio = (wert / Decimal(1_000_000)).quantize(Decimal(1), ROUND_HALF_EVEN)
        return f"{_gruppiert(mio, 0)} Mio. {waehrung or ''}".rstrip()
    if anzeige == "kurs":
        # Kurse: höchstens `stellen` Nachkommastellen, mindestens zwei (345,80 statt
        # 345,79998779296875 aus den Gleitkommazahlen von Yahoo)
        q = wert.quantize(Decimal(1).scaleb(-stellen), ROUND_HALF_EVEN).normalize()
        text = format(q, "f")
        nachkomma = len(text.split(".")[1]) if "." in text else 0
        return f"{_gruppiert(q, max(nachkomma, 2))} {waehrung or ''}".rstrip()
    if anzeige in ("faktor", "ganzzahl"):
        return _gruppiert(wert.quantize(Decimal(1).scaleb(-stellen), ROUND_HALF_EVEN), stellen)
    raise ValueError(f"Unbekannte Anzeige: {anzeige}")
