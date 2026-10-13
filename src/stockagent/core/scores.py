"""Qualitäts- und Risiko-Scores (SPEC 3.5) über den Rechenweg (HR-19).

Die Koeffizienten sind Teil der veröffentlichten Modelle und keine eigenen Gewichte. Schwellen
für Warnungen (Piotroski ab 6 solide, Altman-Zonen, Beneish über -1,78) stehen in
`config/metrics.yaml` unter `schwellen` und werden in `data/hinweise.py` ausgewertet.

- Piotroski F-Score: Piotroski (2000), "Value Investing: The Use of Historical Financial
  Statement Information to Separate Winners from Losers", Journal of Accounting Research 38.
- Altman Z'': Altman (1995/2000), Variante für Nicht-Produzenten mit Buchwert des Eigenkapitals.
  Die Variante mit Börsenwert (Z) folgt in Bauschritt 4.
- Beneish M-Score (8 Variablen): Beneish (1999), "The Detection of Earnings Manipulation",
  Financial Analysts Journal 55.
- Der Qualitätskomposit (Asness, Frazzini, Pedersen) braucht Branchenperzentile und folgt in
  Bauschritt 5. Seine Bestandteile sind Kennzahlen aus `core/kennzahlen.py`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from stockagent.core.calc import Rechenweg, Wert
from stockagent.core.kennzahlen import (
    _cp01,
    _opt,
    bruttoergebnis,
    schulden_gesamt,
    split_bereinigt,
    vertrieb_und_verwaltung,
)
from stockagent.core.registry import metric
from stockagent.core.reihen import Reihen


def _punkt(r: Rechenweg, name: str, erfuellt: bool) -> Decimal:
    return r.schritt(f"punkt_{name}", "1" if erfuellt else "0")


def _langfristige_schulden(r: Rechenweg, d: Reihen, t: date) -> Wert:
    if d.hat("debt_noncurrent", t):
        return d.hole("debt_noncurrent", t)
    return _opt(r, d, "debt_long_total", t)


# ------------------------------------------------------------------ Piotroski


def _piotroski_jahr(r: Rechenweg, d: Reihen, t: date) -> dict[str, Decimal]:
    """Bestandteile eines Jahres. Bilanzsumme zu Jahresbeginn wie bei Piotroski (2000)."""
    j = t.isoformat()
    bs_anfang = d.hole("total_assets", d.vorjahr(t))
    r.pruefe("CP-02", f"Bilanzsumme {j} zu Beginn positiv", bs_anfang.wert > 0)
    ni, ocf = d.hole("net_income", t), d.hole("operating_cash_flow", t)
    _cp01(r, t, ni, ocf, d.hole("revenue", t))
    umsatz = d.hole("revenue", t)
    return {
        "roa": r.schritt(f"roa_{j}", "ni / bs_anfang", ni=ni, bs_anfang=bs_anfang),
        "cfo": r.schritt(f"cfo_{j}", "ocf / bs_anfang", ocf=ocf, bs_anfang=bs_anfang),
        "hebel": r.schritt(
            f"hebel_{j}",
            "lang / ((bs_anfang + bs_ende) / 2)",
            lang=_langfristige_schulden(r, d, t),
            bs_anfang=bs_anfang,
            bs_ende=d.hole("total_assets", t),
        ),
        "liquiditaet": r.schritt(
            f"current_ratio_{j}",
            "ua / kv",
            ua=d.hole("current_assets", t),
            kv=d.hole("current_liabilities", t),
        ),
        "aktien": split_bereinigt(r, d, f"aktien_{j}", d.hole("shares_diluted", t), je_aktie=False),
        "marge": r.schritt(
            f"bruttomarge_{j}", "brutto / umsatz", brutto=bruttoergebnis(r, d, t), umsatz=umsatz
        ),
        "umschlag": r.schritt(
            f"umschlag_{j}", "umsatz / bs_anfang", umsatz=umsatz, bs_anfang=bs_anfang
        ),
    }


@metric("piotroski_f_score")
def piotroski_f_score(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    jetzt = _piotroski_jahr(r, d, t)
    vor = _piotroski_jahr(r, d, d.vorjahr(t))
    punkte = {
        "roa_positiv": _punkt(r, "roa_positiv", jetzt["roa"] > 0),
        "cfo_positiv": _punkt(r, "cfo_positiv", jetzt["cfo"] > 0),
        "roa_gestiegen": _punkt(r, "roa_gestiegen", jetzt["roa"] > vor["roa"]),
        "cfo_groesser_roa": _punkt(r, "cfo_groesser_roa", jetzt["cfo"] > jetzt["roa"]),
        "hebel_gesunken": _punkt(r, "hebel_gesunken", jetzt["hebel"] < vor["hebel"]),
        "liquiditaet_gestiegen": _punkt(
            r, "liquiditaet_gestiegen", jetzt["liquiditaet"] > vor["liquiditaet"]
        ),
        "keine_neuen_aktien": _punkt(r, "keine_neuen_aktien", jetzt["aktien"] <= vor["aktien"]),
        "marge_gestiegen": _punkt(r, "marge_gestiegen", jetzt["marge"] > vor["marge"]),
        "umschlag_gestiegen": _punkt(r, "umschlag_gestiegen", jetzt["umschlag"] > vor["umschlag"]),
    }
    score = r.schritt("f_score", " + ".join(punkte), **punkte)
    r.pruefe("CP-07", "F-Score zwischen 0 und 9", 0 <= score <= 9)
    return score


# ------------------------------------------------------------------ Altman Z''


@metric("altman_z_double_prime")
def altman_z_double_prime(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    bs = d.hole("total_assets", t)
    ua, kv = d.hole("current_assets", t), d.hole("current_liabilities", t)
    _cp01(r, t, bs, ua, kv, d.hole("retained_earnings", t), d.hole("ebit", t), d.hole("equity", t))
    r.pruefe("CP-02", "Bilanzsumme positiv", bs.wert > 0)
    schulden = schulden_gesamt(r, d, t)
    r.pruefe("CP-02", "Verbindlichkeiten positiv", schulden > 0)
    x1 = r.schritt("x1", "(ua - kv) / bs", ua=ua, kv=kv, bs=bs)
    x2 = r.schritt(
        "x2", "gewinnruecklagen / bs", gewinnruecklagen=d.hole("retained_earnings", t), bs=bs
    )
    x3 = r.schritt("x3", "ebit / bs", ebit=d.hole("ebit", t), bs=bs)
    x4 = r.schritt("x4", "ek / schulden", ek=d.hole("equity", t), schulden=schulden)
    return r.schritt(
        "z_double_prime",
        "6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4",
        x1=x1,
        x2=x2,
        x3=x3,
        x4=x4,
    )


# ------------------------------------------------------------------ Beneish


def _beneish_jahr(r: Rechenweg, d: Reihen, t: date) -> dict[str, Decimal]:
    j = t.isoformat()
    umsatz, bs = d.hole("revenue", t), d.hole("total_assets", t)
    _cp01(r, t, umsatz, bs, d.hole("receivables", t), d.hole("ppe_net", t))
    r.pruefe("CP-02", f"Umsatz und Bilanzsumme {j} positiv", umsatz.wert > 0 and bs.wert > 0)
    abschreibung, sachanlagen = d.hole("depreciation", t), d.hole("ppe_net", t)
    return {
        "forderungsquote": r.schritt(
            f"forderungen_zu_umsatz_{j}", "f / u", f=d.hole("receivables", t), u=umsatz
        ),
        "bruttomarge": r.schritt(f"bruttomarge_{j}", "b / u", b=bruttoergebnis(r, d, t), u=umsatz),
        "qualitaet_aktiva": r.schritt(
            f"weiche_aktiva_{j}",
            "1 - (ua + sachanlagen + wertpapiere) / bs",
            ua=d.hole("current_assets", t),
            sachanlagen=sachanlagen,
            wertpapiere=_opt(r, d, "lt_securities", t),
            bs=bs,
        ),
        "umsatz": r.schritt(f"umsatz_{j}", "u", u=umsatz),
        "abschreibungsrate": r.schritt(
            f"abschreibungsrate_{j}", "a / (a + s)", a=abschreibung, s=sachanlagen
        ),
        "vertriebsquote": r.schritt(
            f"vertrieb_zu_umsatz_{j}", "v / u", v=vertrieb_und_verwaltung(r, d, t), u=umsatz
        ),
        "hebel": r.schritt(
            f"hebel_{j}",
            "(kv + lang) / bs",
            kv=d.hole("current_liabilities", t),
            lang=_langfristige_schulden(r, d, t),
            bs=bs,
        ),
    }


@metric("beneish_m_score")
def beneish_m_score(r: Rechenweg, d: Reihen, t: date) -> Decimal:
    jetzt = _beneish_jahr(r, d, t)
    vor = _beneish_jahr(r, d, d.vorjahr(t))
    for name in (
        "forderungsquote",
        "bruttomarge",
        "qualitaet_aktiva",
        "abschreibungsrate",
        "vertriebsquote",
        "hebel",
    ):
        r.pruefe("CP-02", f"{name} im Vorjahr ungleich null", vor[name] != 0)
    r.pruefe("CP-02", "Bruttomarge ungleich null", jetzt["bruttomarge"] != 0)
    r.pruefe("CP-02", "Abschreibungsrate ungleich null", jetzt["abschreibungsrate"] != 0)
    idx = {
        "dsri": r.schritt("dsri", "a / b", a=jetzt["forderungsquote"], b=vor["forderungsquote"]),
        "gmi": r.schritt("gmi", "a / b", a=vor["bruttomarge"], b=jetzt["bruttomarge"]),
        "aqi": r.schritt("aqi", "a / b", a=jetzt["qualitaet_aktiva"], b=vor["qualitaet_aktiva"]),
        "sgi": r.schritt("sgi", "a / b", a=jetzt["umsatz"], b=vor["umsatz"]),
        "depi": r.schritt(
            "depi", "a / b", a=vor["abschreibungsrate"], b=jetzt["abschreibungsrate"]
        ),
        "sgai": r.schritt("sgai", "a / b", a=jetzt["vertriebsquote"], b=vor["vertriebsquote"]),
        "tata": r.schritt(
            "tata",
            "(ni - ocf) / bs",
            ni=d.hole("net_income", t),
            ocf=d.hole("operating_cash_flow", t),
            bs=d.hole("total_assets", t),
        ),
        "lvgi": r.schritt("lvgi", "a / b", a=jetzt["hebel"], b=vor["hebel"]),
    }
    return r.schritt(
        "m_score",
        "-4.84 + 0.920 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi + 0.115 * depi"
        " - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi",
        **idx,
    )
