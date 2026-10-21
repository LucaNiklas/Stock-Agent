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


def aktien_aus_eps(
    aktien: Mapping[date, Eingabe],
    ergebnis: Mapping[date, Eingabe],
    eps: Mapping[date, Eingabe],
) -> dict[date, Eingabe]:
    """Verwässerte Aktienzahl je Stichtag, fehlende Jahre aus Ergebnis der Aktionäre /
    verwässertem Ergebnis je Aktie (ESEF: TotalEnergies, Enel, Iberdrola melden keine
    Aktienzahl). Nur bei gleicher Währung und Ergebnis ungleich 0. Das Ergebnis je Aktie ist auf
    Cent gerundet, die Abweichung liegt meist unter 0,1 %."""
    out = dict(aktien)
    for t, e in ergebnis.items():
        k = eps.get(t)
        if t in out or k is None or k.wert == 0 or e.wert == 0 or e.waehrung != k.waehrung:
            continue
        out[t] = Eingabe(
            wert=e.wert / k.wert,
            quelle=f"abgeleitet: Aktien = Ergebnis / Ergebnis je Aktie verwässert "
            f"({e.quelle}; {k.quelle})",
            einheit="shares",
            periode_ende=t,
            waehrung=None,
            periode_start=e.periode_start,
            veroeffentlicht=e.veroeffentlicht,
        )
    return out
