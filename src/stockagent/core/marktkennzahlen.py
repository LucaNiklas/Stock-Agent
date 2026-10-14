"""Bewertungskennzahlen mit Börsenkurs (SPEC 3.3, Bauschritt 4).

Gleiche Regeln wie `core/kennzahlen.py`: schrittweise über den Rechenweg, Prüfpunkte nach jedem
Abschnitt (HR-19), Definitionen in `config/metrics.yaml`.

Konventionen:

- Kurs zum Stichtag ist der Schlusskurs am Geschäftsjahresende oder am letzten Handelstag davor
  (Yahoo, ADR 0005). Für den aktuellen Stand setzt `metrics_update.py` den letzten Schlusskurs
  ein (Statistik `aktuell`).
- Weicht die Kurswährung von der Berichtswährung ab, wird der Kurs zum Referenzkurs der EZB am
  Kurstag in die Berichtswährung umgerechnet (`core/fx.py`), Unterwährungen wie Pence vorher.
  Verhältniszahlen sind davon unabhängig. SPEC 5.2 Nr. 4 rechnet die Marktkapitalisierung in
  Kurswährung, das Ergebnis der Verhältniszahlen ist dasselbe.
- Aktienzahl ist die verwässerte durchschnittliche Aktienzahl des Geschäftsjahres, um Splits
  bereinigt wie die Kurse. Rückkäufe nach dem Stichtag sind darin nicht enthalten.
- Unternehmenswert = Börsenwert + Nettoverschuldung (mit Leasing) + Pensionsdefizit +
  Minderheitsanteile − at-equity-Beteiligungen, mit Brücke zurück zum Börsenwert (CP-03).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from stockagent.core import fx
from stockagent.core.calc import Eingabe, NichtDefiniert, Rechenweg
from stockagent.core.kennzahlen import (
    _cp01,
    _opt,
    _quote,
    ebit_wert,
    fcf_wert,
    nettoverschuldung,
    split_bereinigt,
)
from stockagent.core.registry import metric
from stockagent.core.reihen import Reihen


def berichtswaehrung(d: Reihen, t: date) -> str | None:
    for name in ("revenue", "equity", "total_assets"):
        if d.hat(name, t) and d.hole(name, t).waehrung:
            return d.hole(name, t).waehrung
    return None


def kurs(r: Rechenweg, d: Reihen, t: date) -> Eingabe:
    """Schlusskurs zum Stichtag in Berichtswährung, mit Umrechnung im Rechenweg."""
    k = d.hole("kurs", t)
    _cp01(r, t, k)
    r.pruefe("CP-02", "Kurs positiv", k.wert > 0)
    ziel = berichtswaehrung(d, t)
    if ziel is None or k.waehrung == ziel:
        return k
    unter = dict(d.parameter.get("unterwaehrungen", {}))
    benoetigt = {fx.hauptwaehrung(str(k.waehrung), unter), ziel} - {"EUR"}
    kurse = {w: d.hole(f"fx_{w}", t) for w in benoetigt}
    return fx.umrechnen(r, "kurs_in_berichtswaehrung", k, ziel, kurse, unter)


def _aktien(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    aktien = split_bereinigt(r, d, "aktien", d.hole("shares_diluted", t), je_aktie=False)
    r.pruefe("CP-02", "Aktienzahl positiv", aktien > 0)
    return aktien


def boersenwert(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    k = kurs(r, d, t)
    aktien = _aktien(r, d, t)
    return r.schritt("boersenwert", "kurs * aktien", kurs=k, aktien=aktien)


def unternehmenswert(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    bw = boersenwert(r, d, t)
    nd = nettoverschuldung(r, d, t)
    ausfinanzierung = _opt(r, d, "pension_funded_status", t)
    if d.hat("equity_incl_nci", t) and d.hat("equity", t):
        minderheiten = r.schritt(
            "minderheitsanteile",
            "ek_gesamt - ek_aktionaere",
            ek_gesamt=d.hole("equity_incl_nci", t),
            ek_aktionaere=d.hole("equity", t),
        )
    else:
        minderheiten = r.schritt("minderheitsanteile_nicht_gemeldet", "0")
    beteiligungen = _opt(r, d, "equity_investments", t)
    ev = r.schritt(
        "unternehmenswert",
        "boersenwert + nettoverschuldung - ausfinanzierung + minderheiten - beteiligungen",
        boersenwert=bw,
        nettoverschuldung=nd,
        ausfinanzierung=ausfinanzierung,
        minderheiten=minderheiten,
        beteiligungen=beteiligungen,
    )
    # Brücke rückwärts: aus dem Unternehmenswert muss wieder der Börsenwert entstehen (CP-03)
    zurueck = r.schritt(
        "bruecke_zum_boersenwert",
        "ev - nettoverschuldung + ausfinanzierung - minderheiten + beteiligungen",
        ev=ev,
        nettoverschuldung=nd,
        ausfinanzierung=ausfinanzierung,
        minderheiten=minderheiten,
        beteiligungen=beteiligungen,
    )
    r.pruefe("CP-03", "Brücke Unternehmenswert -> Börsenwert geht auf", zurueck == bw)
    return ev


def _je_boersenwert(r: Rechenweg, d: Reihen, t: date, name: str, zaehler: Decimal) -> Decimal:
    return _quote(r, name, zaehler, boersenwert(r, d, t), "Börsenwert")


@metric("market_cap")
def market_cap(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return boersenwert(r, d, t)


@metric("enterprise_value")
def enterprise_value(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return unternehmenswert(r, d, t)


@metric("pe")
def pe(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    k = kurs(r, d, t)
    eps_roh = d.hole("eps_diluted", t)
    _cp01(r, t, eps_roh)
    eps = split_bereinigt(r, d, "eps", eps_roh, je_aktie=True)
    if eps <= 0:
        raise NichtDefiniert(f"KGV nur bei positivem Gewinn je Aktie ({eps})")
    return _quote(r, "kgv", k, eps, "Gewinn je Aktie")


@metric("ev_ebit")
def ev_ebit(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ev = unternehmenswert(r, d, t)
    return _quote(r, "ev_ebit", ev, ebit_wert(r, d, t), "EBIT", wirtschaftlich=True)


@metric("ev_sales")
def ev_sales(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ev = unternehmenswert(r, d, t)
    umsatz = d.hole("revenue", t)
    _cp01(r, t, umsatz)
    return _quote(r, "ev_umsatz", ev, umsatz, "Umsatz", wirtschaftlich=True)


@metric("fcf_yield")
def fcf_yield(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return _je_boersenwert(r, d, t, "fcf_rendite", fcf_wert(r, d, t))


@metric("pb")
def pb(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    bw = boersenwert(r, d, t)
    ek = d.hole("equity", t)
    _cp01(r, t, ek)
    return _quote(r, "kurs_buchwert", bw, ek, "Eigenkapital", wirtschaftlich=True)


@metric("dividend_yield")
def dividend_yield(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    div = d.hole("dividends_paid", t)
    _cp01(r, t, div)
    r.pruefe("CP-02", "Dividenden als Auszahlung nicht negativ", div.wert >= 0)
    return _je_boersenwert(r, d, t, "dividendenrendite", r.schritt("dividenden", "d", d=div))


def _netto_rueckkauf(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    rueck = d.hole("buybacks", t)
    _cp01(r, t, rueck)
    r.pruefe("CP-02", "Rückkäufe als Auszahlung nicht negativ", rueck.wert >= 0)
    return r.schritt(
        "netto_rueckkauf",
        "rueckkauf - ausgabe",
        rueckkauf=rueck,
        ausgabe=_opt(r, d, "stock_issuance", t),
    )


@metric("buyback_yield")
def buyback_yield(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return _je_boersenwert(r, d, t, "rueckkaufrendite", _netto_rueckkauf(r, d, t))


@metric("shareholder_yield")
def shareholder_yield(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    div = d.hole("dividends_paid", t)
    _cp01(r, t, div)
    vorjahr = d.vorjahr(t)
    nd_vor = nettoverschuldung(r, d, vorjahr)
    nd = nettoverschuldung(r, d, t)
    summe = r.schritt(
        "an_kapitalgeber",
        "dividenden + netto_rueckkauf + (nd_vorjahr - nd)",
        dividenden=div,
        netto_rueckkauf=_netto_rueckkauf(r, d, t),
        nd_vorjahr=nd_vor,
        nd=nd,
    )
    return _je_boersenwert(r, d, t, "aktionaersrendite", summe)
