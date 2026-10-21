"""Mohanram G-Score für die Scorecard Wachstum ohne Gewinn (SPEC 3.11, ADR 0010).

Acht Signale, je 1 wenn erfüllt, relativ zum Median der Vergleichsgruppe (Mohanram 2005,
Review of Accounting Studies):

- G1 Gesamtkapitalrendite über dem Median, G2 operativer Cashflow zu Bilanzsumme über dem Median,
- G3 operativer Cashflow größer als der Jahresüberschuss (absolut, ohne Median),
- G4 Streuung der Gesamtkapitalrendite unter dem Median, G5 Streuung des Umsatzwachstums unter
  dem Median,
- G6 F&E, G7 Investitionen, G8 Werbung, je zu Bilanzsumme, über dem Median.

Abweichung von Mohanram: Streuungen aus Jahreswerten statt Quartalen (Trendstatistik `stdabw`,
mindestens 5 Jahre). Fehlt einer Firma ein Signal, zählt es nicht. Der Wert ist der Anteil der
erfüllten an den vorhandenen Signalen (0 bis 1), damit Firmen mit unterschiedlich vielen
Angaben vergleichbar bleiben. Unter 4 vorhandenen Signalen kein Wert.

Gerechnet wird beim Benoten für die Firma und jede Firma der Vergleichsgruppe über denselben
Median, Schritt für Schritt im Rechenweg (HR-19).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

from stockagent.core.calc import NichtDefiniert, Rechenweg, rechne

VERSION = "1.0"
Schluessel = tuple[str, str]
KENNZAHL: Schluessel = ("mohanram_g_score", "wert")
MINDEST_SIGNALE = 4

# (Signal, Kennzahl, Statistik, Richtung gegen den Median: hoch = darüber erfüllt)
SIGNALE: tuple[tuple[str, str, str, str], ...] = (
    ("G1", "roa", "wert", "hoch"),
    ("G2", "ocf_to_assets", "wert", "hoch"),
    ("G4", "roa", "stdabw", "niedrig"),
    ("G5", "revenue_growth", "stdabw", "niedrig"),
    ("G6", "rd_to_assets", "wert", "hoch"),
    ("G7", "capex_to_assets", "wert", "hoch"),
    ("G8", "advertising_to_assets", "wert", "hoch"),
)


def mediane(
    r: Rechenweg, alle: Sequence[Mapping[Schluessel, Decimal | None]]
) -> dict[Schluessel, Decimal]:
    out: dict[Schluessel, Decimal] = {}
    for signal, kennzahl, statistik, _ in SIGNALE:
        werte = [v for w in alle if (v := w.get((kennzahl, statistik))) is not None]
        if werte:
            out[(kennzahl, statistik)] = r.median(f"median_{signal}_{kennzahl}_{statistik}", werte)
    return out


def g_score(
    subjekt: str,
    stichtag: str,
    eigene: Mapping[Schluessel, Decimal | None],
    median: Mapping[Schluessel, Decimal],
) -> tuple[Decimal | None, dict[str, object]]:
    """G-Score einer Firma gegen die Mediane der Gruppe. Zurück Wert und Rechenweg."""
    r = Rechenweg("mohanram_g_score", VERSION, subjekt, stichtag, pflicht=("CP-07",))

    def rechnung(r: Rechenweg) -> Decimal:
        erfuellt = vorhanden = Decimal(0)
        for signal, kennzahl, statistik, richtung in SIGNALE:
            wert, m = eigene.get((kennzahl, statistik)), median.get((kennzahl, statistik))
            if wert is None or m is None:
                continue
            ja = wert > m if richtung == "hoch" else wert < m
            erfuellt = r.schritt(
                f"{signal}_{kennzahl}_{statistik}",
                "e + j",
                e=erfuellt,
                j=int(ja),
                wert=wert,
                median=m,
            )
            vorhanden = r.schritt(f"{signal}_vorhanden", "v + 1", v=vorhanden)
        ocf = eigene.get(("ocf_to_net_income", "wert"))
        if ocf is not None:
            # G3: operativer Cashflow größer als der Jahresüberschuss. Die Quote ocf / ni ist
            # über 1 nur bei positivem Jahresüberschuss definiert, sonst fehlt sie
            erfuellt = r.schritt("G3_ocf_groesser_ergebnis", "e + j", e=erfuellt, j=int(ocf > 1))
            vorhanden = r.schritt("G3_vorhanden", "v + 1", v=vorhanden)
        r.pruefe("CP-07", "erfüllte Signale höchstens vorhandene", erfuellt <= vorhanden)
        if vorhanden < MINDEST_SIGNALE:
            raise NichtDefiniert(f"nur {vorhanden} von 8 Signalen vorhanden")
        return r.schritt("g_score", "erfuellt / vorhanden", erfuellt=erfuellt, vorhanden=vorhanden)

    e = rechne(r, rechnung)
    return e.wert, e.rechenweg


def ergaenzen(
    subjekt: str,
    stichtag: str,
    eigene: Mapping[Schluessel, Decimal | None],
    gruppe: Sequence[Mapping[Schluessel, Decimal | None]],
) -> tuple[
    dict[Schluessel, Decimal | None], list[dict[Schluessel, Decimal | None]], dict[str, object]
]:
    """Firma und Gruppe um den G-Score ergänzen (Median über Firma und Gruppe)."""
    r = Rechenweg("mohanram_mediane", VERSION, subjekt, stichtag, pflicht=())
    median = mediane(r, [eigene, *gruppe])
    wert, weg = g_score(subjekt, stichtag, eigene, median)
    neu_eigen = {**eigene, KENNZAHL: wert}
    neu_gruppe = [{**g, KENNZAHL: g_score(subjekt, stichtag, g, median)[0]} for g in gruppe]
    return (
        neu_eigen,
        neu_gruppe,
        {"mediane": {f"{k[0]}_{k[1]}": str(v) for k, v in median.items()}, "firma": weg},
    )
