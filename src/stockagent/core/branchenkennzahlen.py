"""Kennzahlen der Branchen-Scorecards (SPEC 3.11, Bauschritt 8, ADR 0010).

Banken, Versicherer, Immobilien, Versorger, Wachstum ohne Gewinn und Holdings. Gleiche Regeln
wie `core/kennzahlen.py`: schrittweise über den Rechenweg, Prüfpunkte nach jedem Abschnitt
(HR-19), Definitionen und Pflicht-Prüfpunkte in `config/metrics.yaml`.

Konventionen:

- Materielles Eigenkapital (Banken) = Eigenkapital der Aktionäre − Vorzugskapital −
  Geschäftswert − übrige immaterielle Werte. Meldet die Firma Geschäftswert und immaterielle
  Werte in einem Posten (HSBC, ING), gilt dieser.
- Eigenkapitalkosten von Banken und Versicherern: risikofreier Zins + Beta der Branche laut
  Damodaran (wie gemessen, ohne Umrechnung über die Verschuldung) * Risikoprämie. Die
  Verschuldung ist dort Teil des Geschäfts, das Hamada-Verfahren der übrigen Firmen passt nicht.
- Gerechtfertigtes Kurs-Buchwert-Verhältnis nach der Residualgewinnlogik:
  (Rendite − g) / (Eigenkapitalkosten − g), g aus `config/metrics.yaml` (parameter). Die
  Kennzahl ist der Abstand dazu: gerechtfertigt / tatsächlich − 1 (positiv = günstig).
- FFO nach NAREIT, angenähert aus XBRL: Ergebnis der Stammaktionäre + Abschreibungen +
  Wertminderungen auf Immobilien − Gewinne aus Immobilienverkäufen. Die Abschreibungen enthalten
  auch solche auf nicht immobilienbezogene Werte (Vermerk).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from stockagent.core.calc import EingabeFehlt, NichtDefiniert, Rechenweg, Wert
from stockagent.core.kennzahlen import (
    _cp01,
    _durchschnitt,
    _opt,
    _quote,
    _w,
    ebitda,
    fcf_wert,
    nettoverschuldung,
    schulden_gesamt,
    split_bereinigt,
)
from stockagent.core.marktkennzahlen import boersenwert, dividenden, unternehmenswert
from stockagent.core.registry import metric
from stockagent.core.reihen import Reihen

# ------------------------------------------------------------------ Hilfen


def _parameter(d: Reihen, name: str, t: date) -> Decimal:
    """Feste Annahme aus config/metrics.yaml (parameter), als Eingabe mit Quelle."""
    return d.hole(f"parameter_{name}", t).wert


def _immateriell(r: Rechenweg, d: Reihen, t: date) -> Wert:
    if d.hat("goodwill_and_intangibles", t):
        return d.hole("goodwill_and_intangibles", t)
    return r.schritt(
        f"geschaeftswert_und_immaterielle_{t.isoformat()}",
        "geschaeftswert + immaterielle",
        geschaeftswert=_opt(r, d, "goodwill", t),
        immaterielle=_opt(r, d, "intangibles_ex_goodwill", t),
    )


def materielles_eigenkapital(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ek = d.hole("equity", t)
    _cp01(r, t, ek)
    immateriell = _immateriell(r, d, t)
    vorzug = _opt(r, d, "preferred_equity", t)
    r.pruefe(
        "CP-02",
        "Vorzugskapital und immaterielle Werte nicht negativ",
        _w(vorzug) >= 0 and _w(immateriell) >= 0,
    )
    return r.schritt(
        f"materielles_eigenkapital_{t.isoformat()}",
        "ek - vorzugskapital - immateriell",
        ek=ek,
        vorzugskapital=vorzug,
        immateriell=immateriell,
    )


def _ergebnis_stammaktionaere(r: Rechenweg, d: Reihen, t: date) -> Wert:
    if d.hat("net_income_common", t):
        ni = d.hole("net_income_common", t)
    else:
        ni = d.hole("net_income", t)
        r.vermerk(
            "ERGEBNIS_VOR_VORZUG: kein Ergebnis der Stammaktionäre gemeldet, Jahresüberschuss "
            "vor Vorzugsdividenden"
        )
    _cp01(r, t, ni)
    return ni


def _kredite_durchschnitt(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    if not (d.hole("loans", t).wert > 0 and d.hole("loans", d.vorjahr(t)).wert > 0):
        raise NichtDefiniert("Kreditbestand am Anfang oder Ende nicht positiv")
    r.pruefe("CP-02", "Kreditbestand am Anfang und Ende positiv", True)
    return _durchschnitt(r, d, "loans", t)


def eigenkapitalkosten_branche(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    """Eigenkapitalkosten Banken und Versicherer: rf + Beta der Branche * Risikoprämie."""
    rf_p = d.hole("rf", t)
    r.pruefe("CP-02", "Risikofreier Zins zwischen -2 % und 20 %", Decimal(-2) < rf_p.wert < 20)
    erp = d.hole("erp", t)
    r.pruefe("CP-02", "Risikoprämie zwischen 0 und 15 %", 0 < erp.wert < Decimal("0.15"))
    beta = d.hole("beta_branche", t)
    r.pruefe("CP-02", "Branchenbeta zwischen 0 und 3", 0 < beta.wert < 3)
    rf = r.schritt("rf", "zins_prozent / 100", zins_prozent=rf_p)
    ke = r.schritt("eigenkapitalkosten", "rf + beta * erp", rf=rf, beta=beta, erp=erp)
    r.pruefe("CP-02", "Eigenkapitalkosten über dem risikofreien Zins", ke > rf)
    return ke


def _abstand_zum_gerechtfertigten(
    r: Rechenweg, d: Reihen, t: date, rendite: Decimal, verhaeltnis: Decimal, name: str
) -> Decimal:
    """Residualgewinnlogik: gerechtfertigtes Verhältnis (rendite - g) / (ke - g), Abstand des
    tatsächlichen Verhältnisses dazu (positiv = Kurs unter dem gerechtfertigten Wert)."""
    ke = eigenkapitalkosten_branche(r, d, t)
    g = _parameter(d, "residualgewinn_wachstum", t)
    r.pruefe("CP-02", "Eigenkapitalkosten über dem Wachstum g", ke > g)
    gerechtfertigt = r.schritt(
        f"{name}_gerechtfertigt", "(rendite - g) / (ke - g)", rendite=rendite, g=g, ke=ke
    )
    if gerechtfertigt <= 0:
        raise NichtDefiniert(
            f"Rendite ({rendite}) unter dem Wachstum g, gerechtfertigtes Verhältnis nicht positiv"
        )
    r.pruefe("CP-02", f"{name}: tatsächliches Verhältnis positiv", verhaeltnis > 0)
    return r.schritt(
        f"{name}_abstand",
        "gerechtfertigt / tatsaechlich - 1",
        gerechtfertigt=gerechtfertigt,
        tatsaechlich=verhaeltnis,
    )


# ------------------------------------------------------------------ Banken


@metric("rote")
def rote(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ni = _ergebnis_stammaktionaere(r, d, t)
    ende = materielles_eigenkapital(r, d, t)
    anfang = materielles_eigenkapital(r, d, d.vorjahr(t))
    if not (anfang > 0 and ende > 0):
        raise NichtDefiniert("Materielles Eigenkapital am Anfang oder Ende nicht positiv")
    r.pruefe("CP-02", "Materielles Eigenkapital am Anfang und Ende positiv", True)
    durchschnitt = r.schritt(
        "materielles_eigenkapital_durchschnitt", "(anfang + ende) / 2", anfang=anfang, ende=ende
    )
    return r.schritt("rote", "ergebnis / materielles_ek", ergebnis=ni, materielles_ek=durchschnitt)


@metric("cost_income_ratio")
def cost_income_ratio(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    kosten = d.hole("noninterest_expense", t)
    zins = d.hole("net_interest_income", t)
    uebrige = d.hole("noninterest_income", t)
    _cp01(r, t, kosten, zins, uebrige)
    ertraege = r.schritt(
        "ertraege",
        "zinsueberschuss + uebrige_ertraege",
        zinsueberschuss=zins,
        uebrige_ertraege=uebrige,
    )
    q = _quote(r, "kosten_ertrag", kosten, ertraege, "Erträge", wirtschaftlich=True)
    r.pruefe("CP-02", "Kosten-Ertrags-Verhältnis nicht negativ", q >= 0)
    return q


@metric("tce_ratio")
def tce_ratio(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    bs = d.hole("total_assets", t)
    _cp01(r, t, bs)
    tce = materielles_eigenkapital(r, d, t)
    materiell = r.schritt(
        "materielle_bilanzsumme",
        "bilanzsumme - immateriell",
        bilanzsumme=bs,
        immateriell=_immateriell(r, d, t),
    )
    q = _quote(r, "tce_quote", tce, materiell, "Materielle Bilanzsumme")
    r.pruefe("CP-02", "TCE-Quote höchstens 100 %", q <= 1)
    return q


@metric("credit_cost_ratio")
def credit_cost_ratio(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    vorsorge = d.hole("credit_provision", t)
    _cp01(r, t, vorsorge, d.hole("loans", t))
    return r.schritt(
        "risikokosten",
        "vorsorge / kredite",
        vorsorge=vorsorge,
        kredite=_kredite_durchschnitt(r, d, t),
    )


@metric("net_charge_off_ratio")
def net_charge_off_ratio(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ausfall = d.hole("net_charge_offs", t)
    _cp01(r, t, ausfall, d.hole("loans", t))
    r.pruefe("CP-02", "Nettoausbuchungen nicht negativ", ausfall.wert >= 0)
    return r.schritt(
        "ausfallquote",
        "ausbuchungen / kredite",
        ausbuchungen=ausfall,
        kredite=_kredite_durchschnitt(r, d, t),
    )


@metric("allowance_to_loans")
def allowance_to_loans(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    vorsorge, kredite = d.hole("loan_allowance", t), d.hole("loans", t)
    _cp01(r, t, vorsorge, kredite)
    q = _quote(r, "vorsorgebestand", vorsorge, kredite, "Kreditbestand")
    r.pruefe("CP-02", "Vorsorgebestand zwischen 0 und 100 % der Kredite", 0 <= q <= 1)
    return q


@metric("deposit_share")
def deposit_share(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    einlagen = d.hole("deposits", t)
    _cp01(r, t, einlagen)
    q = _quote(r, "einlagenanteil", einlagen, schulden_gesamt(r, d, t), "Verbindlichkeiten")
    r.pruefe("CP-02", "Einlagenanteil zwischen 0 und 100 %", 0 <= q <= 1)
    return q


def _je_aktie(r: Rechenweg, d: Reihen, t: date, name: str, zaehler: Wert) -> Decimal:
    aktien = split_bereinigt(r, d, f"aktien_{t.isoformat()}", d.hole("shares_diluted", t), False)
    return _quote(r, name, zaehler, aktien, "Aktienanzahl")


@metric("tangible_book_per_share")
def tangible_book_per_share(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return _je_aktie(r, d, t, "materieller_buchwert_je_aktie", materielles_eigenkapital(r, d, t))


@metric("p_tbv")
def p_tbv(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    bw = boersenwert(r, d, t)
    return _quote(
        r,
        "kurs_materieller_buchwert",
        bw,
        materielles_eigenkapital(r, d, t),
        "Materielles Eigenkapital",
        wirtschaftlich=True,
    )


@metric("p_tbv_gap")
def p_tbv_gap(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return _abstand_zum_gerechtfertigten(r, d, t, rote(r, d, t), p_tbv(r, d, t), "p_tbv")


# ------------------------------------------------------------------ Versicherer


def _praemien(r: Rechenweg, d: Reihen, t: date) -> Wert:
    p = d.hole("premiums_earned", t)
    _cp01(r, t, p)
    r.pruefe("CP-02", "Verdiente Prämien positiv", p.wert > 0)
    return p


@metric("loss_ratio")
def loss_ratio(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    schaeden = d.hole("claims_incurred", t)
    praemien = _praemien(r, d, t)
    _cp01(r, t, schaeden)
    q = _quote(r, "schadenquote", schaeden, praemien, "Verdiente Prämien")
    r.pruefe("CP-02", "Schadenquote zwischen 0 und 300 %", 0 <= q <= 3)
    return q


@metric("reserve_development")
def reserve_development(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    abwicklung = d.hole("prior_year_development", t)
    praemien = _praemien(r, d, t)
    _cp01(r, t, abwicklung)
    q = _quote(r, "reserveabwicklung", abwicklung, praemien, "Verdiente Prämien")
    r.pruefe(
        "CP-02", "Reserveabwicklung zwischen -50 % und 50 % der Prämien", abs(q) <= Decimal("0.5")
    )
    return q


@metric("investment_yield")
def investment_yield(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ertrag = d.hole("net_investment_income", t)
    _cp01(r, t, ertrag, d.hole("investments", t))
    anlagen = _durchschnitt(r, d, "investments", t)
    q = _quote(r, "kapitalanlagerendite", ertrag, anlagen, "Kapitalanlagen")
    r.pruefe(
        "CP-02",
        "Kapitalanlagerendite zwischen -20 % und 30 %",
        Decimal("-0.2") <= q <= Decimal("0.3"),
    )
    return q


@metric("book_value_per_share")
def book_value_per_share(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ek = d.hole("equity", t)
    _cp01(r, t, ek)
    return _je_aktie(r, d, t, "buchwert_je_aktie", ek)


@metric("pb_gap")
def pb_gap(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    from stockagent.core.kennzahlen import roe
    from stockagent.core.marktkennzahlen import pb

    return _abstand_zum_gerechtfertigten(r, d, t, roe(r, d, t), pb(r, d, t), "pb")


# ------------------------------------------------------------------ Immobilien


def ffo_wert(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ni = _ergebnis_stammaktionaere(r, d, t)
    ab = d.hole("depreciation", t)
    _cp01(r, t, ab)
    r.vermerk(
        "FFO_ANGENAEHERT: FFO nach NAREIT aus XBRL, Abschreibungen einschließlich solcher auf "
        "nicht immobilienbezogene Werte"
    )
    return r.schritt(
        "ffo",
        "ergebnis + abschreibungen + wertminderungen - verkaufsgewinne",
        ergebnis=ni,
        abschreibungen=ab,
        wertminderungen=_opt(r, d, "real_estate_impairment", t),
        verkaufsgewinne=_opt(r, d, "real_estate_gains", t),
    )


@metric("ffo")
def ffo(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return ffo_wert(r, d, t)


@metric("ffo_per_share")
def ffo_per_share(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return _je_aktie(r, d, t, "ffo_je_aktie", ffo_wert(r, d, t))


@metric("ffo_yield")
def ffo_yield(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return _quote(r, "ffo_rendite", ffo_wert(r, d, t), boersenwert(r, d, t), "Börsenwert")


@metric("ffo_payout")
def ffo_payout(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    div = dividenden(r, d, t)
    return _quote(
        r,
        "ffo_ausschuettung",
        r.schritt("dividenden", "d", d=div),
        ffo_wert(r, d, t),
        "FFO",
        wirtschaftlich=True,
    )


@metric("ltv")
def ltv(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    immobilien = d.hole("real_estate_net", t)
    _cp01(r, t, immobilien)
    q = _quote(r, "beleihungsquote", nettoverschuldung(r, d, t), immobilien, "Immobilienbestand")
    r.pruefe("CP-02", "Beleihungsquote unter 200 %", q < 2)
    return q


# ------------------------------------------------------------------ Versorger und allgemein


@metric("ev_ebitda")
def ev_ebitda(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ev = unternehmenswert(r, d, t)
    _cp01(r, t, d.hole("depreciation", t))
    return _quote(r, "ev_ebitda", ev, ebitda(r, d, t), "EBITDA", wirtschaftlich=True)


@metric("dividend_cover")
def dividend_cover(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ni = d.hole("net_income", t)
    _cp01(r, t, ni)
    div = dividenden(r, d, t)
    if _w(div) == 0:
        raise NichtDefiniert("keine Dividende gezahlt, Deckung nicht aussagekräftig")
    return _quote(r, "dividendendeckung", ni, r.schritt("dividenden", "d", d=div), "Dividenden")


# ------------------------------------------------------------------ Wachstum ohne Gewinn


def _zur_bilanzsumme(r: Rechenweg, d: Reihen, t: date, name: str, zaehler: Wert) -> Decimal:
    _cp01(r, t, d.hole("total_assets", t))
    bs = _durchschnitt(r, d, "total_assets", t)
    return _quote(r, name, zaehler, bs, "Durchschnittliche Bilanzsumme")


@metric("ocf_to_assets")
def ocf_to_assets(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ocf = d.hole("operating_cash_flow", t)
    _cp01(r, t, ocf)
    return _zur_bilanzsumme(r, d, t, "ocf_zu_bilanzsumme", ocf)


@metric("rd_to_assets")
def rd_to_assets(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    fe = d.hole("rd_expense", t)
    _cp01(r, t, fe)
    return _zur_bilanzsumme(r, d, t, "fe_zu_bilanzsumme", fe)


@metric("capex_to_assets")
def capex_to_assets(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    capex = d.hole("capex", t)
    _cp01(r, t, capex)
    return _zur_bilanzsumme(r, d, t, "investitionen_zu_bilanzsumme", capex)


@metric("advertising_to_assets")
def advertising_to_assets(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    werbung = d.hole("advertising_expense", t)
    _cp01(r, t, werbung)
    return _zur_bilanzsumme(r, d, t, "werbung_zu_bilanzsumme", werbung)


@metric("revenue_growth")
def revenue_growth(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ende, anfang = d.hole("revenue", t), d.hole("revenue", d.vorjahr(t))
    r.pruefe("CP-01", "eine Währung", ende.waehrung == anfang.waehrung)
    if anfang.wert <= 0:
        raise NichtDefiniert("Vorjahresumsatz nicht positiv")
    r.pruefe("CP-02", "Vorjahresumsatz positiv", True)
    return r.schritt("umsatzwachstum", "ende / anfang - 1", ende=ende, anfang=anfang)


@metric("cash_runway_months")
def cash_runway_months(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    """Monate, die Kasse und kurzfristige Wertpapiere beim Mittelabfluss des Jahres reichen.
    Ohne Mittelabfluss die Höchstgrenze aus config/metrics.yaml (Vermerk)."""
    kasse = d.hole("cash", t)
    _cp01(r, t, kasse)
    grenze = _parameter(d, "liquiditaet_hoechst_monate", t)
    mittel = r.schritt(
        "liquide_mittel",
        "kasse + wertpapiere",
        kasse=kasse,
        wertpapiere=_opt(r, d, "st_investments", t),
    )
    r.pruefe("CP-02", "Liquide Mittel nicht negativ", mittel >= 0)
    fcf = fcf_wert(r, d, t)
    if fcf >= 0:
        r.vermerk("KEIN_MITTELABFLUSS: Free Cashflow nicht negativ, Reichweite = Höchstgrenze")
        return r.schritt("reichweite_hoechstgrenze", "grenze", grenze=grenze)
    monate = r.schritt("reichweite", "mittel / (0 - fcf) * 12", mittel=mittel, fcf=fcf)
    return r.schritt("reichweite_begrenzt", "min(monate, grenze)", monate=monate, grenze=grenze)


@metric("ev_sales_to_growth")
def ev_sales_to_growth(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    from stockagent.core.kennzahlen import _umsatz_cagr

    ev = unternehmenswert(r, d, t)
    umsatz = d.hole("revenue", t)
    _cp01(r, t, umsatz)
    ev_umsatz = _quote(r, "ev_umsatz", ev, umsatz, "Umsatz", wirtschaftlich=True)
    wachstum = _umsatz_cagr(r, d, t, 3)
    if wachstum <= 0:
        raise NichtDefiniert(f"Umsatzwachstum 3 Jahre nicht positiv ({wachstum})")
    r.pruefe("CP-02", "Umsatzwachstum positiv", True)
    return r.schritt(
        "ev_umsatz_zu_wachstum",
        "ev_umsatz / (wachstum * 100)",
        ev_umsatz=ev_umsatz,
        wachstum=wachstum,
    )


# ------------------------------------------------------------------ Holdings


@metric("holding_share")
def holding_share(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    """Anteil der at-equity-Beteiligungen an der Bilanzsumme (Regel Holding, SPEC 3.11)."""
    if not d.hat("equity_investments", t):
        raise EingabeFehlt("equity_investments", t.isoformat())
    beteiligungen, bs = d.hole("equity_investments", t), d.hole("total_assets", t)
    _cp01(r, t, beteiligungen, bs)
    q = _quote(r, "beteiligungsquote", beteiligungen, bs, "Bilanzsumme")
    r.pruefe("CP-02", "Beteiligungsquote zwischen 0 und 100 %", 0 <= q <= 1)
    return q
