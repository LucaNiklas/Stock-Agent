"""Kennzahlen aus SPEC 3.3 ohne Börsenkurs (Bauschritt 3). Bewertungskennzahlen folgen in Schritt 4.

Jede Funktion bekommt einen Rechenweg, die Jahresreihen und den Stichtag und rechnet in
benannten Schritten mit Prüfpunkten (HR-19, SPEC 12.7). Definitionen, Eingaben und Pflicht-
Prüfpunkte stehen in `config/metrics.yaml`. Konventionen:

- Durchschnitt eines Bestands = (Vorjahresende + Jahresende) / 2 (SPEC 3.3).
- Optionale Eingaben (`optionale_eingaben` in metrics.yaml) zählen 0, wenn die Firma sie nicht
  meldet. Das steht als eigener Schritt im Rechenweg. Pflicht-Eingaben fehlen nie still: Die
  Kennzahl wird unknown mit Grund (HR-05).
- Aktienzahl und Gewinn je Aktie werden um Splits bereinigt, wenn der Wert vor dem Split
  veröffentlicht wurde (SPEC 3.2 Nr. 8).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from stockagent.core.calc import Eingabe, EingabeFehlt, Rechenweg, Wert
from stockagent.core.registry import metric
from stockagent.core.reihen import Reihen

TOLERANZ_ZWEITER_WEG = Decimal("0.005")  # CP-04, SPEC 12.7
STEUERSATZ_MAX = Decimal("0.35")  # SPEC 12.2, Beispiel roic

# ------------------------------------------------------------------ Hilfen


def _cp01(r: Rechenweg, stichtag: date, *werte: Eingabe) -> None:
    """CP-01: eine Währung und alle Werte zum selben Geschäftsjahr."""
    waehrungen = {w.waehrung for w in werte if w.waehrung is not None}
    r.pruefe("CP-01", f"eine Währung {sorted(waehrungen)}", len(waehrungen) <= 1)
    r.pruefe(
        "CP-01",
        f"alle Werte zum Geschäftsjahr bis {stichtag}",
        all(w.periode_ende == stichtag for w in werte),
    )


def _opt(r: Rechenweg, d: Reihen, name: str, t: date) -> Wert:
    """Optionale Eingabe: gemeldet oder 0 mit Vermerk im Rechenweg."""
    if d.hat(name, t):
        return d.hole(name, t)
    return r.schritt(f"{name}_nicht_gemeldet", "0")


def _vergleich(r: Rechenweg, name: str, a: Decimal, b: Decimal) -> None:
    """CP-04: zwei Wege, Abweichung höchstens 0,5 Prozent."""
    if a == 0:
        r.pruefe("CP-04", f"{name}: zweiter Weg gleich", b == 0)
        return
    abw = r.schritt(f"{name}_abweichung", "abs(a - b) / abs(a)", a=a, b=b)
    r.pruefe("CP-04", f"{name}: zwei Wege, Abweichung höchstens 0,5 %", abw <= TOLERANZ_ZWEITER_WEG)


def _durchschnitt(r: Rechenweg, d: Reihen, name: str, t: date) -> Decimal:
    ende = d.hole(name, t)
    anfang = d.hole(name, d.vorjahr(t))
    r.pruefe("CP-01", f"{name}: Anfang und Ende in einer Währung", anfang.waehrung == ende.waehrung)
    return r.schritt(f"{name}_durchschnitt", "(anfang + ende) / 2", anfang=anfang, ende=ende)


def bruttoergebnis(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    """Bruttoergebnis gemeldet oder Umsatz minus Umsatzkosten, bei beiden Wegen Gegenrechnung."""
    hat_brutto = d.hat("gross_profit", t)
    hat_teile = d.hat("revenue", t) and d.hat("cost_of_revenue", t)
    if hat_teile:
        aus_teilen = r.schritt(
            "brutto_aus_teilen",
            "umsatz - umsatzkosten",
            umsatz=d.hole("revenue", t),
            umsatzkosten=d.hole("cost_of_revenue", t),
        )
    if hat_brutto:
        brutto = r.schritt("bruttoergebnis", "b", b=d.hole("gross_profit", t))
        if hat_teile:
            _vergleich(r, "bruttoergebnis", brutto, aus_teilen)
        return brutto
    if hat_teile:
        return aus_teilen
    raise EingabeFehlt("gross_profit oder cost_of_revenue", t.isoformat())


def finanzschulden(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    """Finanzschulden aus Teilen. Weg A: LongTermDebt gesamt, Weg B: lang- plus kurzfristig.

    Kurzfristige Kredite und Commercial Paper kommen in beiden Wegen dazu (0, wenn nicht
    gemeldet). Liegen beide Wege vor, müssen sie übereinstimmen (CP-04).
    """
    kurz = r.schritt(
        "kredite_und_cp",
        "kredite + cp",
        kredite=_opt(r, d, "short_term_borrowings", t),
        cp=_opt(r, d, "commercial_paper", t),
    )
    weg_a = weg_b = None
    if d.hat("debt_long_total", t):
        weg_a = r.schritt(
            "finanzschulden_weg_a",
            "lang_gesamt + kurz",
            lang_gesamt=d.hole("debt_long_total", t),
            kurz=kurz,
        )
    if d.hat("debt_noncurrent", t):
        weg_b = r.schritt(
            "finanzschulden_weg_b",
            "langfristig + kurzfristig_faellig + kurz",
            langfristig=d.hole("debt_noncurrent", t),
            kurzfristig_faellig=_opt(r, d, "debt_current", t),
            kurz=kurz,
        )
    if weg_a is not None and weg_b is not None:
        _vergleich(r, "finanzschulden", weg_a, weg_b)
    ergebnis = weg_a if weg_a is not None else weg_b
    if ergebnis is None:
        raise EingabeFehlt("Finanzschulden (LongTermDebt oder LongTermDebtNoncurrent)", str(t))
    return ergebnis


def leasing(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    """Leasingverbindlichkeiten: Operating plus Finance, gesamt oder aus kurz- und langfristig."""

    def art(prefix: str) -> Wert:
        if d.hat(prefix, t):
            return d.hole(prefix, t)
        if d.hat(f"{prefix}_current", t) or d.hat(f"{prefix}_noncurrent", t):
            return r.schritt(
                f"{prefix}_aus_teilen",
                "kurz + lang",
                kurz=_opt(r, d, f"{prefix}_current", t),
                lang=_opt(r, d, f"{prefix}_noncurrent", t),
            )
        return r.schritt(f"{prefix}_nicht_gemeldet", "0")

    return r.schritt(
        "leasing",
        "operating + finance",
        operating=art("lease_operating"),
        finance=art("lease_finance"),
    )


def schulden_gesamt(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    if d.hat("total_liabilities", t):
        return r.schritt("schulden_gesamt", "s", s=d.hole("total_liabilities", t))
    return r.schritt(
        "schulden_aus_passiva",
        "passiva - eigenkapital_mit_minderheiten",
        passiva=d.hole("liabilities_and_equity", t),
        eigenkapital_mit_minderheiten=d.hole("equity_incl_nci", t),
    )


def vertrieb_und_verwaltung(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    if d.hat("sga", t):
        return r.schritt("vertrieb_und_verwaltung", "s", s=d.hole("sga", t))
    return r.schritt(
        "vertrieb_und_verwaltung_aus_teilen",
        "vertrieb + verwaltung",
        vertrieb=d.hole("selling_marketing", t),
        verwaltung=d.hole("general_admin", t),
    )


def fcf_wert(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ocf = d.hole("operating_cash_flow", t)
    capex = d.hole("capex", t)
    _cp01(r, t, ocf, capex)
    return r.schritt(
        "fcf",
        "ocf - capex - capex_immateriell",
        ocf=ocf,
        capex=capex,
        capex_immateriell=_opt(r, d, "capex_intangibles", t),
    )


def ebitda(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return r.schritt(
        "ebitda",
        "ebit + abschreibungen",
        ebit=d.hole("ebit", t),
        abschreibungen=d.hole("depreciation", t),
    )


def split_bereinigt(r: Rechenweg, d: Reihen, name: str, w: Eingabe, je_aktie: bool) -> Decimal:
    """Aktienzahl mal Faktor, Wert je Aktie geteilt durch Faktor, je Split nach der Meldung."""
    wert: Decimal = w.wert
    for s in d.splits:
        if w.veroeffentlicht is not None and w.veroeffentlicht < s.wirksam_ab:
            formel = "wert / faktor" if je_aktie else "wert * faktor"
            wert = r.schritt(f"{name}_split_{s.verhaeltnis}", formel, wert=wert, faktor=s.faktor)
    return wert


def _quote(r: Rechenweg, name: str, zaehler: Wert, nenner: Wert, nenner_text: str) -> Decimal:
    r.pruefe("CP-02", f"{nenner_text} positiv", _w(nenner) > 0)
    return r.schritt(name, "zaehler / nenner", zaehler=zaehler, nenner=nenner)


def _w(v: Wert) -> Decimal:
    return v.wert if isinstance(v, Eingabe) else Decimal(v)


def _cagr(r: Rechenweg, anfang: Wert, ende: Wert, jahre: int) -> Decimal:
    r.pruefe("CP-02", "Anfangs- und Endwert positiv", _w(anfang) > 0 and _w(ende) > 0)
    faktor = r.schritt("faktor", "ende / anfang", ende=ende, anfang=anfang)
    wachstum = r.potenz("faktor_je_jahr", faktor, 1, jahre)
    return r.schritt("cagr", "faktor_je_jahr - 1", faktor_je_jahr=wachstum)


def _marge(r: Rechenweg, d: Reihen, t: date, zaehler: Wert) -> Decimal:
    umsatz = d.hole("revenue", t)
    if isinstance(zaehler, Eingabe):
        _cp01(r, t, zaehler, umsatz)
    else:
        _cp01(r, t, umsatz)
    m = _quote(r, "marge", zaehler, umsatz, "Umsatz")
    r.pruefe("CP-02", "Marge höchstens 100 %", m <= 1)
    return m


# ------------------------------------------------------------------ Profitabilität


@metric("gross_margin")
def gross_margin(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return _marge(r, d, t, bruttoergebnis(r, d, t))


@metric("ebit_margin")
def ebit_margin(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return _marge(r, d, t, d.hole("ebit", t))


@metric("fcf_margin")
def fcf_margin(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return _marge(r, d, t, fcf_wert(r, d, t))


@metric("gp_to_assets")
def gp_to_assets(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    bilanzsumme = d.hole("total_assets", t)
    _cp01(r, t, bilanzsumme)
    return _quote(r, "gp_to_assets", bruttoergebnis(r, d, t), bilanzsumme, "Bilanzsumme")


def _roe_direkt_und_dupont(r: Rechenweg, d: Reihen, t: date) -> tuple[Decimal, Decimal]:
    ni, umsatz = d.hole("net_income", t), d.hole("revenue", t)
    _cp01(r, t, ni, umsatz, d.hole("equity", t), d.hole("total_assets", t))
    r.pruefe(
        "CP-02",
        "Eigenkapital am Anfang und Ende positiv",
        d.hole("equity", t).wert > 0 and d.hole("equity", d.vorjahr(t)).wert > 0,
    )
    ek = _durchschnitt(r, d, "equity", t)
    bs = _durchschnitt(r, d, "total_assets", t)
    direkt = r.schritt("roe_direkt", "ni / ek", ni=ni, ek=ek)
    nettomarge = _quote(r, "nettomarge", ni, umsatz, "Umsatz")
    umschlag = r.schritt("kapitalumschlag", "umsatz / bs", umsatz=umsatz, bs=bs)
    hebel = r.schritt("hebel", "bs / ek", bs=bs, ek=ek)
    dupont_wert = r.schritt(
        "roe_dupont",
        "nettomarge * umschlag * hebel",
        nettomarge=nettomarge,
        umschlag=umschlag,
        hebel=hebel,
    )
    _vergleich(r, "roe", direkt, dupont_wert)
    return direkt, dupont_wert


@metric("roe")
def roe(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return _roe_direkt_und_dupont(r, d, t)[0]


@metric("dupont")
def dupont(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return _roe_direkt_und_dupont(r, d, t)[1]


@metric("roa")
def roa(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ni = d.hole("net_income", t)
    _cp01(r, t, ni, d.hole("total_assets", t))
    bs = _durchschnitt(r, d, "total_assets", t)
    return _quote(r, "roa", ni, bs, "Durchschnittliche Bilanzsumme")


def _investiertes_kapital(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return r.schritt(
        f"investiertes_kapital_{t.isoformat()}",
        "ek + finanzschulden + leasing - kasse",
        ek=d.hole("equity", t),
        finanzschulden=finanzschulden(r, d, t),
        leasing=leasing(r, d, t),
        kasse=d.hole("cash", t),
    )


@metric("roic")
def roic(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ebit, steuer, vorsteuer = d.hole("ebit", t), d.hole("income_tax", t), d.hole("pretax_income", t)
    _cp01(r, t, ebit, steuer, vorsteuer, d.hole("equity", t), d.hole("cash", t))
    if vorsteuer.wert > 0:
        roh = r.schritt("steuersatz_roh", "steuer / vorsteuer", steuer=steuer, vorsteuer=vorsteuer)
    else:
        roh = r.schritt("steuersatz_bei_verlust", "0")
    satz = r.schritt("steuersatz", "min(max(roh, 0), grenze)", roh=roh, grenze=STEUERSATZ_MAX)
    r.pruefe("CP-02", "Steuersatz zwischen 0 und 0,35", 0 <= satz <= STEUERSATZ_MAX)
    nopat = r.schritt("nopat", "ebit * (1 - satz)", ebit=ebit, satz=satz)
    ende = _investiertes_kapital(r, d, t)
    anfang = _investiertes_kapital(r, d, d.vorjahr(t))
    ic = r.schritt(
        "investiertes_kapital_durchschnitt", "(anfang + ende) / 2", anfang=anfang, ende=ende
    )
    return _quote(r, "roic", nopat, ic, "Investiertes Kapital")


# ------------------------------------------------------------------ Wachstum


def _umsatz_cagr(r: Rechenweg, d: Reihen, t: date, jahre: int) -> Decimal:
    ende, anfang = d.hole("revenue", t), d.hole("revenue", d.vorjahr(t, jahre))
    r.pruefe("CP-01", "eine Währung", ende.waehrung == anfang.waehrung)
    return _cagr(r, anfang, ende, jahre)


@metric("revenue_cagr_3y")
def revenue_cagr_3y(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return _umsatz_cagr(r, d, t, 3)


@metric("revenue_cagr_5y")
def revenue_cagr_5y(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return _umsatz_cagr(r, d, t, 5)


@metric("eps_cagr_5y")
def eps_cagr_5y(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    t0 = d.vorjahr(t, 5)
    ende, anfang = d.hole("eps_diluted", t), d.hole("eps_diluted", t0)
    r.pruefe("CP-01", "eine Währung", ende.waehrung == anfang.waehrung)
    return _cagr(
        r,
        split_bereinigt(r, d, "eps_anfang", anfang, je_aktie=True),
        split_bereinigt(r, d, "eps_ende", ende, je_aktie=True),
        5,
    )


def _fcf_je_aktie(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    fcf = fcf_wert(r, d, t)
    aktien = split_bereinigt(
        r, d, f"aktien_{t.isoformat()}", d.hole("shares_diluted", t), je_aktie=False
    )
    return _quote(r, f"fcf_je_aktie_{t.isoformat()}", fcf, aktien, "Aktienanzahl")


@metric("fcf_per_share_cagr_5y")
def fcf_per_share_cagr_5y(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return _cagr(r, _fcf_je_aktie(r, d, d.vorjahr(t, 5)), _fcf_je_aktie(r, d, t), 5)


@metric("share_count_change_3y")
def share_count_change_3y(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    t0 = d.vorjahr(t, 3)
    ende = split_bereinigt(r, d, "aktien_ende", d.hole("shares_diluted", t), je_aktie=False)
    anfang = split_bereinigt(r, d, "aktien_anfang", d.hole("shares_diluted", t0), je_aktie=False)
    r.pruefe("CP-02", "Aktienanzahl positiv", anfang > 0 and ende > 0)
    return r.schritt("veraenderung", "ende / anfang - 1", ende=ende, anfang=anfang)


# ------------------------------------------------------------------ Cashflow und Ertragsqualität


@metric("fcf")
def fcf(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return fcf_wert(r, d, t)


def _zu_jahresueberschuss(r: Rechenweg, d: Reihen, t: date, zaehler: Wert) -> Decimal:
    ni = d.hole("net_income", t)
    _cp01(r, t, ni)
    return _quote(r, "quote", zaehler, ni, "Jahresüberschuss")


@metric("fcf_conversion")
def fcf_conversion(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return _zu_jahresueberschuss(r, d, t, fcf_wert(r, d, t))


@metric("ocf_to_net_income")
def ocf_to_net_income(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ocf = d.hole("operating_cash_flow", t)
    _cp01(r, t, ocf)
    return _zu_jahresueberschuss(r, d, t, ocf)


@metric("sloan_accruals")
def sloan_accruals(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ni, ocf = d.hole("net_income", t), d.hole("operating_cash_flow", t)
    _cp01(r, t, ni, ocf, d.hole("total_assets", t))
    accruals = r.schritt("accruals", "ni - ocf", ni=ni, ocf=ocf)
    bs = _durchschnitt(r, d, "total_assets", t)
    return _quote(r, "sloan_accruals", accruals, bs, "Durchschnittliche Bilanzsumme")


@metric("sbc_to_revenue")
def sbc_to_revenue(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    sbc = d.hole("sbc", t)
    return _marge(r, d, t, sbc)


@metric("fcf_after_sbc")
def fcf_after_sbc(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    sbc = d.hole("sbc", t)
    _cp01(r, t, sbc)
    return r.schritt("fcf_nach_sbc", "fcf - sbc", fcf=fcf_wert(r, d, t), sbc=sbc)


# ------------------------------------------------------------------ Bilanz und Finanzierung


def nettoverschuldung(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    kasse = d.hole("cash", t)
    _cp01(r, t, kasse)
    return r.schritt(
        "nettoverschuldung",
        "finanzschulden + leasing - kasse - wertpapiere_kurzfristig",
        finanzschulden=finanzschulden(r, d, t),
        leasing=leasing(r, d, t),
        kasse=kasse,
        wertpapiere_kurzfristig=_opt(r, d, "st_investments", t),
    )


@metric("net_debt")
def net_debt(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return nettoverschuldung(r, d, t)


@metric("net_debt_incl_pensions")
def net_debt_incl_pensions(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    # Ausfinanzierungsstatus negativ = Defizit, das wie eine Schuld wirkt
    return r.schritt(
        "nettoverschuldung_mit_pensionen",
        "nettoverschuldung - ausfinanzierung",
        nettoverschuldung=nettoverschuldung(r, d, t),
        ausfinanzierung=_opt(r, d, "pension_funded_status", t),
    )


@metric("net_debt_to_ebitda")
def net_debt_to_ebitda(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    _cp01(r, t, d.hole("ebit", t), d.hole("depreciation", t))
    return _quote(r, "net_debt_to_ebitda", nettoverschuldung(r, d, t), ebitda(r, d, t), "EBITDA")


@metric("interest_coverage")
def interest_coverage(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ebit, zinsen = d.hole("ebit", t), d.hole("interest_expense", t)
    _cp01(r, t, ebit, zinsen)
    return _quote(r, "zinsdeckung", ebit, zinsen, "Zinsaufwand")


@metric("current_ratio")
def current_ratio(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ua, kv = d.hole("current_assets", t), d.hole("current_liabilities", t)
    _cp01(r, t, ua, kv)
    return _quote(r, "current_ratio", ua, kv, "Kurzfristige Verbindlichkeiten")


@metric("quick_ratio")
def quick_ratio(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ua, kv = d.hole("current_assets", t), d.hole("current_liabilities", t)
    _cp01(r, t, ua, kv)
    ohne = r.schritt("ohne_vorraete", "ua - vorraete", ua=ua, vorraete=_opt(r, d, "inventory", t))
    return _quote(r, "quick_ratio", ohne, kv, "Kurzfristige Verbindlichkeiten")


@metric("equity_ratio")
def equity_ratio(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ek, bs = d.hole("equity", t), d.hole("total_assets", t)
    _cp01(r, t, ek, bs)
    q = _quote(r, "eigenkapitalquote", ek, bs, "Bilanzsumme")
    r.pruefe("CP-02", "Eigenkapitalquote höchstens 100 %", q <= 1)
    return q


@metric("debt_maturity_12m")
def debt_maturity_12m(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    kasse = d.hole("cash", t)
    _cp01(r, t, kasse)
    faellig = r.schritt(
        "faellig_12m",
        "faellige_langfristige + kredite + cp",
        faellige_langfristige=_opt(r, d, "debt_current", t),
        kredite=_opt(r, d, "short_term_borrowings", t),
        cp=_opt(r, d, "commercial_paper", t),
    )
    deckung = r.schritt(
        "deckung", "kasse + kreditlinien", kasse=kasse, kreditlinien=_opt(r, d, "credit_lines", t)
    )
    return _quote(r, "debt_maturity_12m", faellig, deckung, "Kasse plus Kreditlinien")


# ------------------------------------------------------------------ Kapitalallokation


@metric("payout_fcf")
def payout_fcf(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    ausschuettung = r.schritt(
        "ausschuettung",
        "dividenden + rueckkaeufe",
        dividenden=_opt(r, d, "dividends_paid", t),
        rueckkaeufe=_opt(r, d, "buybacks", t),
    )
    return _quote(r, "payout_fcf", ausschuettung, fcf_wert(r, d, t), "Free Cashflow")


@metric("capex_to_depreciation")
def capex_to_depreciation(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    capex, ab = d.hole("capex", t), d.hole("depreciation", t)
    _cp01(r, t, capex, ab)
    return _quote(r, "capex_to_depreciation", capex, ab, "Abschreibungen")


@metric("acquisition_intensity")
def acquisition_intensity(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    jahre = [t] + [d.vorjahr(t, i) for i in range(1, 5)]
    uebernahmen: dict[str, Wert] = {}
    ocf: dict[str, Wert] = {}
    for i, j in enumerate(jahre):
        uebernahmen[f"u{i}"] = _opt(r, d, "acquisitions", j)
        ocf[f"o{i}"] = d.hole("operating_cash_flow", j)
    summe_u = r.schritt("uebernahmen_5j", " + ".join(uebernahmen), **uebernahmen)
    summe_o = r.schritt("ocf_5j", " + ".join(ocf), **ocf)
    r.pruefe("CP-01", "eine Währung", len({_w2(o) for o in ocf.values()}) <= 1)
    return _quote(r, "acquisition_intensity", summe_u, summe_o, "Operativer Cashflow 5 Jahre")


def _w2(v: Wert) -> str | None:
    return v.waehrung if isinstance(v, Eingabe) else None
