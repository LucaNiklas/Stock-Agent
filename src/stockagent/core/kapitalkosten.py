"""Kapitalkosten, Reverse-DCF, normalisiertes EV/EBIT und Altman Z (SPEC 3.4 bis 3.6, ADR 0006).

Regeln wie in `core/kennzahlen.py`: schrittweise über den Rechenweg, Prüfpunkte nach jedem
Abschnitt (HR-19), Schwellen und Annahmen aus `config/kapitalkosten.yaml` (als Eingaben mit
Quelle in den Reihen, `data/inputs.py`).

Kapitalkosten (WACC):

- Eigenkapitalkosten = risikofreier Zins + Beta (verschuldet) * Aktienrisikoprämie.
- Beta: Branchenbeta nach Damodaran, unverschuldet und um Kasse bereinigt, mit der eigenen
  Verschuldung neu verschuldet (Hamada): beta_u * (1 + (1 - Steuersatz) * FK / EK).
  EK = Börsenwert, FK = Finanzschulden + Leasing.
- Fremdkapitalkosten = risikofreier Zins + Aufschlag. Aufschlag aus dem synthetischen Rating
  nach Zinsdeckung (EBIT / Zinsaufwand, Tabelle von Damodaran). Meldet die Firma keinen
  Zinsaufwand, gilt der Aufschlag ihrer Branche laut Damodaran (Vermerk).
- Gewichte nach Marktwerten: EK / (EK + FK) und FK / (EK + FK).

Reverse-DCF (Hauptverfahren der Bewertung): das Wachstum des freien Cashflows für die Firma
(FCFF = FCF + Zinsaufwand * (1 - Steuersatz)) über 10 Jahre, bei dem der Barwert samt Endwert
den Unternehmenswert ergibt. Ist der FCFF null oder negativ, wird auf Umsatzbasis gerechnet:
Umsatz * Zielmarge, Zielmarge vorerst der Median der eigenen FCF-Margen der letzten 10 Jahre
(Branchenmedian ab Schritt 5, Vermerk). Rückrechnung CP-06.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from stockagent.core import dcf
from stockagent.core.calc import Eingabe, EingabeFehlt, NichtDefiniert, Rechenweg, Wert
from stockagent.core.kennzahlen import (
    _cp01,
    _opt,
    _quote,
    ebit_wert,
    fcf_wert,
    finanzschulden,
    leasing,
    schulden_gesamt,
)
from stockagent.core.marktkennzahlen import boersenwert, unternehmenswert
from stockagent.core.registry import metric
from stockagent.core.reihen import Reihen


@dataclass(frozen=True)
class Kapitalkosten:
    wacc: Decimal
    rf: Decimal
    steuer: Wert


def _rating(d: Reihen, deckung: Decimal) -> dict[str, str]:
    """Zeile der Damodaran-Tabelle für diese Zinsdeckung: die mit der höchsten Untergrenze, die
    die Deckung nicht übersteigt (die Tabelle hat Lücken wie 0,199999 bis 0,2)."""
    art = "finanz" if d.parameter.get("finanzfirma") else "nichtfinanz"
    tabelle = [z for z in d.parameter.get("ratings", []) if z["art"] == art]
    if not tabelle:
        raise EingabeFehlt("Rating-Tabelle von Damodaran (stockagent markt update)", art)
    passend = [z for z in tabelle if Decimal(z["ab"]) <= deckung]
    return max(passend, key=lambda z: Decimal(z["ab"])) if passend else tabelle[0]


def kapitalkosten(r: Rechenweg, d: Reihen, t: date) -> Kapitalkosten:
    rf_p = d.hole("rf", t)
    r.pruefe("CP-02", "Risikofreier Zins zwischen -2 % und 20 %", Decimal(-2) < rf_p.wert < 20)
    rf = r.schritt("rf", "zins_prozent / 100", zins_prozent=rf_p)
    erp = d.hole("erp", t)
    r.pruefe("CP-02", "Risikoprämie zwischen 0 und 15 %", 0 < erp.wert < Decimal("0.15"))
    beta_u = d.hole("beta_unverschuldet", t)
    r.pruefe("CP-02", "Branchenbeta zwischen 0 und 3", 0 < beta_u.wert < 3)
    steuer = d.hole("steuersatz", t)
    r.pruefe("CP-02", "Steuersatz zwischen 0 und 50 %", 0 <= steuer.wert < Decimal("0.5"))
    for v in d.parameter.get("vermerke_kapitalkosten", ()):
        r.vermerk(v)

    # Abschnitt 1: Eigenkapitalkosten
    ek = boersenwert(r, d, t)
    r.pruefe("CP-02", "Börsenwert positiv", ek > 0)
    fk = r.schritt(
        "fremdkapital",
        "finanzschulden + leasing",
        finanzschulden=finanzschulden(r, d, t),
        leasing=leasing(r, d, t),
    )
    r.pruefe("CP-02", "Fremdkapital nicht negativ", fk >= 0)
    beta_l = r.schritt(
        "beta_verschuldet",
        "beta_u * (1 + (1 - steuer) * fk / ek)",
        beta_u=beta_u,
        steuer=steuer,
        fk=fk,
        ek=ek,
    )
    ke = r.schritt("eigenkapitalkosten", "rf + beta * erp", rf=rf, beta=beta_l, erp=erp)
    r.pruefe("CP-02", "Eigenkapitalkosten über dem risikofreien Zins", ke > rf)

    # Abschnitt 2: Fremdkapitalkosten
    zinsen = d.werte.get("interest_expense", {}).get(t)
    if zinsen is not None and zinsen.wert > 0:
        _cp01(r, t, zinsen)
        deckung = r.schritt("zinsdeckung", "ebit / zinsen", ebit=ebit_wert(r, d, t), zinsen=zinsen)
        z = _rating(d, deckung)
        aufschlag_p = Eingabe(
            Decimal(z["aufschlag"]),
            f"Damodaran ratings ({z['stand']}): Zinsdeckung über {z['ab']} bis {z['bis']} -> "
            f"Rating {z['rating']}",
            "prozent",
            t,
        )
        aufschlag = r.schritt("aufschlag", "aufschlag_prozent / 100", aufschlag_prozent=aufschlag_p)
    else:
        kd_branche = d.hole("kd_branche", t)
        rf_damodaran = d.hole("rf_damodaran", t)
        r.vermerk(
            "KD_BRANCHE: kein Zinsaufwand gemeldet, Aufschlag der Branche laut Damodaran "
            f"({kd_branche.quelle})"
        )
        aufschlag = r.schritt(
            "aufschlag_branche",
            "max(kd_branche_prozent / 100 - rf_damodaran, 0)",
            kd_branche_prozent=kd_branche,
            rf_damodaran=rf_damodaran,
        )
    r.pruefe("CP-02", "Aufschlag zwischen 0 und 25 %", 0 <= aufschlag < Decimal("0.25"))
    kd = r.schritt("fremdkapitalkosten", "rf + aufschlag", rf=rf, aufschlag=aufschlag)
    kd_n = r.schritt("fremdkapitalkosten_nach_steuern", "kd * (1 - steuer)", kd=kd, steuer=steuer)

    # Abschnitt 3: Gewichte und WACC
    gewicht_ek = r.schritt("gewicht_ek", "ek / (ek + fk)", ek=ek, fk=fk)
    gewicht_fk = r.schritt("gewicht_fk", "fk / (ek + fk)", ek=ek, fk=fk)
    summe = r.schritt("gewichte_summe", "a + b", a=gewicht_ek, b=gewicht_fk)
    r.pruefe("CP-03", "Gewichte ergeben 1", abs(summe - 1) < Decimal("1e-20"))
    wacc = r.schritt("wacc", "ge * ke + gf * kd_n", ge=gewicht_ek, ke=ke, gf=gewicht_fk, kd_n=kd_n)
    r.pruefe("CP-02", "WACC zwischen 1 % und 30 %", Decimal("0.01") < wacc < Decimal("0.30"))
    return Kapitalkosten(wacc, rf, steuer)


@metric("wacc")
def wacc(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    return kapitalkosten(r, d, t).wacc


def _fcff(r: Rechenweg, d: Reihen, t: date, steuer: Wert) -> Decimal:
    fcf = fcf_wert(r, d, t)
    zinsen = _opt(r, d, "interest_expense", t)
    if not d.hat("interest_expense", t):
        r.vermerk("FCFF_OHNE_ZINSEN: kein Zinsaufwand gemeldet, FCFF = FCF")
    return r.schritt("fcff", "fcf + zinsen * (1 - steuer)", fcf=fcf, zinsen=zinsen, steuer=steuer)


def _zielmarge(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    """Median der eigenen FCF-Margen bis zu 10 Jahre (Branchenmedian ab Schritt 5)."""
    margen = []
    for j in d.stichtage[d.stichtage.index(t) :][:10]:
        if not (d.hat("revenue", j) and d.hat("operating_cash_flow", j) and d.hat("capex", j)):
            continue
        umsatz = d.hole("revenue", j)
        if umsatz.wert <= 0:
            continue
        margen.append(
            r.schritt(f"fcf_marge_{j.isoformat()}", "fcf / u", fcf=fcf_wert(r, d, j), u=umsatz)
        )
    if len(margen) < 3:
        raise EingabeFehlt("FCF-Margen für die Zielmarge (mindestens 3 Jahre)", t.isoformat())
    m = r.median("zielmarge", margen)
    if m <= 0:
        raise NichtDefiniert(
            "FCF negativ und Median der eigenen FCF-Margen nicht positiv: kein Reverse-DCF"
        )
    r.vermerk("ZIELMARGE_EIGEN: Zielmarge aus der eigenen Historie, Branchenmedian ab Schritt 5")
    return m


@metric("implied_growth")
def implied_growth(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    cfg = d.parameter.get("kapitalkosten", {})
    if not cfg:
        raise EingabeFehlt("config/kapitalkosten.yaml", t.isoformat())
    k = kapitalkosten(r, d, t)
    end_max = d.hole("endwachstum_max", t)
    g_end = r.schritt("endwachstum", "min(rf, maximum)", rf=k.rf, maximum=end_max)
    if k.wacc <= g_end:
        raise NichtDefiniert(f"WACC {k.wacc} nicht über dem Endwachstum {g_end}")
    ev = unternehmenswert(r, d, t)
    if ev <= 0:
        raise NichtDefiniert("Unternehmenswert nicht positiv (mehr Kasse als Börsenwert)")

    # Abschnitt 1: Basis-Cashflow
    fcff = _fcff(r, d, t, k.steuer)
    if fcff > 0:
        basis = r.schritt("basis_cashflow", "fcff", fcff=fcff)
    else:
        umsatz = d.hole("revenue", t)
        _cp01(r, t, umsatz)
        r.vermerk("UMSATZBASIS: FCFF nicht positiv, implizites Umsatzwachstum bei Zielmarge")
        basis = r.schritt(
            "basis_cashflow", "umsatz * marge", umsatz=umsatz, marge=_zielmarge(r, d, t)
        )

    # Abschnitt 2: Suche nach dem Wachstum
    jahre = int(cfg["jahre"])
    such = cfg["suche"]
    g = dcf.suche_wachstum(
        r,
        "implizites_wachstum",
        ev,
        basis,
        k.wacc,
        g_end,
        jahre,
        Decimal(str(such["wachstum_min"])),
        Decimal(str(such["wachstum_max"])),
        Decimal(str(such["genauigkeit"])),
    )

    # Abschnitt 3: Rückrechnung (CP-06)
    bw = dcf.barwert_rechenweg(r, basis, g, k.wacc, g_end, jahre, "rueckrechnung")
    abweichung = r.schritt("abweichung", "abs(bw - ev) / ev", bw=bw.gesamt, ev=ev)
    toleranz = Decimal(str(cfg["rueckrechnung_toleranz"]))
    r.pruefe(
        "CP-06",
        f"DCF mit implizitem Wachstum trifft den Unternehmenswert (±{toleranz})",
        abweichung <= toleranz,
    )
    return g


@metric("ev_ebit_normalized")
def ev_ebit_normalized(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    cfg = d.parameter.get("kapitalkosten", {}).get("ev_ebit_normalisiert")
    if not cfg:
        raise EingabeFehlt("config/kapitalkosten.yaml ev_ebit_normalisiert", t.isoformat())
    ev = unternehmenswert(r, d, t)
    werte: dict[str, Wert] = {}
    for j in d.stichtage[d.stichtage.index(t) :][: int(cfg["max_jahre"])]:
        try:
            werte[f"ebit_{j:%Y_%m_%d}"] = ebit_wert(r, d, j)
        except EingabeFehlt:
            continue
    mindest = int(cfg["mindest_jahre"])
    if len(werte) < mindest:
        raise EingabeFehlt(
            f"EBIT für mindestens {mindest} Geschäftsjahre (vorhanden {len(werte)})", t.isoformat()
        )
    schnitt = r.schritt("ebit_durchschnitt", f"({' + '.join(werte)}) / {len(werte)}", **werte)
    return _quote(r, "ev_ebit_normalisiert", ev, schnitt, "durchschnittliches EBIT", True)


@metric("altman_z")
def altman_z(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    if not d.parameter.get("produzent"):
        raise NichtDefiniert(
            "Altman Z nur für Produzenten (SIC 2000 bis 3999), für alle anderen gilt Z''"
        )
    bs = d.hole("total_assets", t)
    ua, kv = d.hole("current_assets", t), d.hole("current_liabilities", t)
    umsatz = d.hole("revenue", t)
    _cp01(r, t, bs, ua, kv, d.hole("retained_earnings", t), umsatz)
    r.pruefe("CP-02", "Bilanzsumme positiv", bs.wert > 0)
    schulden = schulden_gesamt(r, d, t)
    r.pruefe("CP-02", "Verbindlichkeiten positiv", schulden > 0)
    x1 = r.schritt("x1", "(ua - kv) / bs", ua=ua, kv=kv, bs=bs)
    x2 = r.schritt(
        "x2", "gewinnruecklagen / bs", gewinnruecklagen=d.hole("retained_earnings", t), bs=bs
    )
    x3 = r.schritt("x3", "ebit / bs", ebit=ebit_wert(r, d, t), bs=bs)
    x4 = r.schritt(
        "x4", "boersenwert / schulden", boersenwert=boersenwert(r, d, t), schulden=schulden
    )
    x5 = r.schritt("x5", "umsatz / bs", umsatz=umsatz, bs=bs)
    return r.schritt(
        "z",
        "1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5",
        x1=x1,
        x2=x2,
        x3=x3,
        x4=x4,
        x5=x5,
    )
