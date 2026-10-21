"""Barwert von Cashflows über einen Prognosezeitraum mit Endwert nach Gordon (SPEC 3.6).

Zwei Wege, die dieselbe Zahl liefern müssen:

- `barwert`: schnelle Rechnung ohne Protokoll, für die Suche nach dem impliziten Wachstum
  (Intervallhalbierung, viele Durchläufe).
- `barwert_rechenweg`: dieselbe Rechnung Jahr für Jahr als Schritte im Rechenweg. Sie dient als
  Rückrechnung (CP-06) und als nachprüfbarer Rechenweg der DCF-Szenarien.

Konvention: Cashflow im Basisjahr `basis` (Jahr 0), Jahr j hat basis * (1 + g)^j, abgezinst mit
(1 + w)^j. Endwert am Ende des Jahres n: cf_n * (1 + g_end) / (w - g_end), abgezinst mit
(1 + w)^n. Werte am Jahresende, keine Halbjahreskonvention.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from stockagent.core.calc import NichtDefiniert, PruefpunktVerletzt, Rechenweg, Schritt, Wert

_PRECISION = 40


def barwert(
    basis: Decimal, wachstum: Decimal, wacc: Decimal, endwachstum: Decimal, jahre: int
) -> Decimal:
    if wacc <= endwachstum:
        raise NichtDefiniert(f"Kapitalkosten {wacc} nicht über dem Endwachstum {endwachstum}")
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        cf, abzinsung, summe = basis, Decimal(1), Decimal(0)
        for _ in range(jahre):
            cf = cf * (1 + wachstum)
            abzinsung = abzinsung * (1 + wacc)
            summe += cf / abzinsung
        endwert = cf * (1 + endwachstum) / (wacc - endwachstum)
        return summe + endwert / abzinsung


@dataclass(frozen=True)
class Barwert:
    gesamt: Decimal
    prognose: Decimal
    endwert_barwert: Decimal
    endwert_anteil: Decimal


def barwert_rechenweg(
    r: Rechenweg,
    basis: Wert,
    wachstum: Wert,
    wacc: Wert,
    endwachstum: Wert,
    jahre: int,
    praefix: str = "dcf",
) -> Barwert:
    """Dieselbe Rechnung wie `barwert`, Jahr für Jahr im Rechenweg."""
    cf: Wert = basis
    abzinsung: Wert = Decimal(1)
    teile: dict[str, Decimal] = {}
    for j in range(1, jahre + 1):
        cf = r.schritt(f"{praefix}_cf_{j}", "cf * (1 + g)", cf=cf, g=wachstum)
        abzinsung = r.schritt(f"{praefix}_abzinsung_{j}", "a * (1 + w)", a=abzinsung, w=wacc)
        teile[f"bw_{j}"] = r.schritt(f"{praefix}_bw_{j}", "cf / a", cf=cf, a=abzinsung)
    prognose = r.schritt(f"{praefix}_prognose", " + ".join(teile), **teile)
    endwert = r.schritt(
        f"{praefix}_endwert", "cf * (1 + g_end) / (w - g_end)", cf=cf, g_end=endwachstum, w=wacc
    )
    ew_bw = r.schritt(f"{praefix}_endwert_barwert", "e / a", e=endwert, a=abzinsung)
    gesamt = r.schritt(f"{praefix}_gesamt", "p + e", p=prognose, e=ew_bw)
    anteil = r.schritt(f"{praefix}_endwert_anteil", "e / g", e=ew_bw, g=gesamt)
    return Barwert(gesamt, prognose, ew_bw, anteil)


def suche_wachstum(
    r: Rechenweg,
    name: str,
    ziel: Decimal,
    basis: Decimal,
    wacc: Decimal,
    endwachstum: Decimal,
    jahre: int,
    unten: Decimal,
    oben: Decimal,
    genauigkeit: Decimal,
) -> Decimal:
    """Wachstum g mit barwert(basis, g, ...) = ziel, per Intervallhalbierung. Der Barwert steigt
    mit g, solange basis positiv ist. Liegt das Ziel außerhalb des Suchbereichs, ist die Größe
    für diese Daten nicht aussagekräftig (NichtDefiniert, kein Datenfehler)."""
    if basis <= 0:
        raise PruefpunktVerletzt(r, "CP-02", f"{name}: Basis-Cashflow muss positiv sein ({basis})")
    w_unten = barwert(basis, unten, wacc, endwachstum, jahre)
    w_oben = barwert(basis, oben, wacc, endwachstum, jahre)
    if ziel < w_unten:
        raise NichtDefiniert(
            f"Der Kurs rechtfertigt weniger als {unten * 100:.0f} % Wachstum je Jahr (Suchbereich)"
        )
    if ziel > w_oben:
        raise NichtDefiniert(
            f"Der Kurs braucht mehr als {oben * 100:.0f} % Wachstum je Jahr (Suchbereich)"
        )
    lo, hi, runden = unten, oben, 0
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        while hi - lo > genauigkeit:
            mitte = (lo + hi) / 2
            if barwert(basis, mitte, wacc, endwachstum, jahre) < ziel:
                lo = mitte
            else:
                hi = mitte
            runden += 1
        g = (lo + hi) / 2
    r.schritte.append(
        Schritt(
            name=name,
            formel=(
                "Intervallhalbierung: g mit Barwert(basis, g, wacc, g_end, "
                f"{jahre} Jahre) = ziel, {runden} Schritte bis Genauigkeit {genauigkeit}"
            ),
            eingaben={
                "ziel": str(ziel),
                "basis": str(basis),
                "wacc": str(wacc),
                "g_end": str(endwachstum),
                "unten": str(unten),
                "oben": str(oben),
            },
            ergebnis=str(g),
        )
    )
    return g
