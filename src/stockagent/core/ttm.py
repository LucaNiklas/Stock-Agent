"""Werte der letzten 12 Monate (TTM) aus Quartalsberichten (SPEC 3.3, 3.4 Nr. 1).

Für Ströme (Umsatz, EBIT, Cashflow, Gewinn je Aktie) gilt
TTM = letztes Geschäftsjahr + seit Jahresbeginn bis zum letzten Quartal
      - derselbe Zeitraum im Vorjahr.
Damit werden keine Quartale doppelt gezählt (SPEC 3.2 Nr. 4), auch wenn die Firma kein viertes
Quartal meldet. Stände (Bilanz) gelten am Ende des letzten Quartals. Die verwässerte Aktienzahl
ist die des letzten Quartals.

Jeder TTM-Wert entsteht über einen eigenen Rechenweg mit Prüfpunkten: gleiche Währung (CP-01),
Vorjahreszeitraum gleich lang und ein Jahr früher (CP-02). Das Ergebnis ist eine `Eingabe`, deren
Quelle die drei Teile nennt. Kennzahlen rechnen damit wie mit einem Geschäftsjahr.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from stockagent.core import dq
from stockagent.core.calc import Eingabe, PruefpunktVerletzt, Rechenweg
from stockagent.core.reihen import Reihen

VERSION = "1.0"
TOLERANZ_TAGE = 7


@dataclass(frozen=True)
class Strom:
    """Teile eines Stroms: Geschäftsjahr, seit Jahresbeginn, Vorjahreszeitraum."""

    gj: Eingabe
    ytd: Eingabe
    ytd_vj: Eingabe


@dataclass(frozen=True)
class Ergebnis:
    werte: dict[str, Eingabe]
    luecken: dict[str, str]


def _strom(subjekt: str, name: str, quartal: date, s: Strom) -> Eingabe:
    r = Rechenweg(f"ttm_{name}", VERSION, subjekt, quartal.isoformat(), pflicht=("CP-01", "CP-02"))
    r.pruefe(
        "CP-01",
        "Geschäftsjahr, laufendes Jahr und Vorjahreszeitraum in derselben Währung",
        s.gj.waehrung == s.ytd.waehrung == s.ytd_vj.waehrung,
    )
    if s.ytd.periode_start is None or s.ytd_vj.periode_start is None:
        raise PruefpunktVerletzt(r, "CP-02", f"{name}: Zeitraum ohne Beginn")
    laenge = dq.dauer_tage(s.ytd.periode_start, s.ytd.periode_ende)
    laenge_vj = dq.dauer_tage(s.ytd_vj.periode_start, s.ytd_vj.periode_ende)
    abstand = dq.dauer_tage(s.ytd_vj.periode_ende, s.ytd.periode_ende)
    r.pruefe(
        "CP-02",
        "Vorjahreszeitraum gleich lang und ein Jahr früher",
        abs(laenge - laenge_vj) <= TOLERANZ_TAGE and 358 <= abstand <= 374,
    )
    wert = r.schritt("ttm", "gj + ytd - ytd_vj", gj=s.gj, ytd=s.ytd, ytd_vj=s.ytd_vj)
    monate = r.schritt("monate", "runde(tage / 30.44)", tage=Decimal(laenge))
    return Eingabe(
        wert,
        f"TTM bis {quartal.isoformat()}: GJ bis {s.gj.periode_ende.isoformat()} ({s.gj.quelle}) "
        f"+ {monate} Monate bis {s.ytd.periode_ende.isoformat()} ({s.ytd.quelle}) "
        f"- {monate} Monate bis {s.ytd_vj.periode_ende.isoformat()} ({s.ytd_vj.quelle})",
        s.ytd.einheit,
        quartal,
        s.ytd.waehrung,
        None,
        max(
            (e.veroeffentlicht for e in (s.gj, s.ytd, s.ytd_vj) if e.veroeffentlicht is not None),
            default=None,
        ),
    )


def ttm_werte(
    subjekt: str, quartal: date, stroeme: dict[str, Strom], staende: dict[str, Eingabe]
) -> Ergebnis:
    werte: dict[str, Eingabe] = {}
    luecken: dict[str, str] = {}
    for name, s in stroeme.items():
        try:
            werte[name] = _strom(subjekt, name, quartal, s)
        except PruefpunktVerletzt as exc:
            luecken[name] = f"TTM nicht berechenbar: {exc}"
    for name, e in staende.items():
        werte[name] = replace(e, periode_ende=quartal)
    return Ergebnis(werte, luecken)


# Eingaben ohne Bezug zu einem Bericht (Zins, Beta, Annahmen), die für den TTM-Stichtag vom
# letzten Geschäftsjahr übernommen werden. Kurs, Zins und Risikoprämie setzt danach
# `data/inputs.reihen_aktuell` auf heute.
KONSTANT = (
    "beta_unverschuldet",
    "steuersatz",
    "kd_branche",
    "rf_damodaran",
    "endwachstum_max",
    "rf",
    "erp",
)


def ttm_reihen(basis: Reihen, quartal: date, ergebnis: Ergebnis) -> Reihen:
    """Die Jahresreihen mit dem TTM-Stichtag vorne (neuestes zuerst)."""
    gj = basis.stichtage[0]
    werte = {name: dict(je) for name, je in basis.werte.items()}
    for name, e in ergebnis.werte.items():
        werte.setdefault(name, {})[quartal] = e
    for name in KONSTANT:
        if gj in werte.get(name, {}):
            werte[name][quartal] = replace(werte[name][gj], periode_ende=quartal)
    luecken = {**basis.luecken, **ergebnis.luecken}
    return replace(basis, stichtage=(quartal, *basis.stichtage), werte=werte, luecken=luecken)
