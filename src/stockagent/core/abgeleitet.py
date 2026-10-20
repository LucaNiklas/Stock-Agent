"""Abgeleitete Eingangsgrößen, wenn ein Bericht eine Größe nicht als Summe meldet (Bauschritt 7).

Umsatz: Manche IFRS-Berichte melden keinen Gesamtumsatz, sondern Produktumsatz und sonstige
Erlöse getrennt (Novartis, Sanofi: `RevenueFromSaleOfGoods` und `OtherRevenue`). Dann gilt
Umsatz = Bruttoergebnis + Umsatzkosten, nur bei gleicher Periode und Währung. Die Quelle nennt
beide Konzepte, die Kennzahlen tragen so den Vermerk der Herkunft.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from stockagent.core.calc import Eingabe


def umsatz_aus_bruttoergebnis(
    umsatz: Mapping[date, Eingabe],
    brutto: Mapping[date, Eingabe],
    kosten: Mapping[date, Eingabe],
) -> dict[date, Eingabe]:
    """Umsatz je Stichtag, fehlende Jahre aus Bruttoergebnis + Umsatzkosten ergänzt."""
    out = dict(umsatz)
    for t, gp in brutto.items():
        k = kosten.get(t)
        if t in out or k is None:
            continue
        if gp.waehrung != k.waehrung or gp.periode_start != k.periode_start:
            continue
        out[t] = Eingabe(
            wert=gp.wert + k.wert,
            quelle=f"abgeleitet: Umsatz = Bruttoergebnis + Umsatzkosten ({gp.quelle}; {k.quelle})",
            einheit=gp.einheit,
            periode_ende=t,
            waehrung=gp.waehrung,
            periode_start=gp.periode_start,
            veroeffentlicht=max(
                (x for x in (gp.veroeffentlicht, k.veroeffentlicht) if x is not None), default=None
            ),
        )
    return out
