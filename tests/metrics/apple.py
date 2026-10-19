"""Apple-Werte für die Handrechnungen, von Hand aus den 10-K-Dokumenten abgelesen (13.10.2026).

Quellen (SEC EDGAR, CIK 0000320193):
- 10-K 2025, Accession 0000320193-25-000079: GuV Seite 29, Bilanz Seite 31, Kapitalfluss
  Seite 33, Leasing Seite 42. Spalten 2025, 2024 (Bilanz), 2025 bis 2023 (GuV, Kapitalfluss).
- 10-K 2024, Accession 0000320193-24-000123: GuV Seite 29, Bilanz Seite 31 (Spalte 2023).
- 10-K 2022, Accession 0000320193-22-000108: GuV Seite 29, Bilanz Seite 31, Kapitalfluss
  Seite 33 (Spalten 2022 bis 2020).
Beträge in Mio. USD wie im Dokument, Aktien in Tausend Stück, EPS in USD je Aktie.
Kurse: Yahoo-Chart AAPL, abgerufen 14.10.2026, Rohdatei SHA-256 6d1ecdd2bee4e25c...; Schlusskurs
am letzten Handelstag vor dem Geschäftsjahresende, Gleitkommazahl wie geliefert.
LongTermDebt (Laufzeitschulden gesamt) steht nicht als eigene Zeile in der Bilanz. Er kommt aus
dem XBRL-Konzept us-gaap:LongTermDebt und entspricht der Summe der beiden Bilanzzeilen „Term
debt“ (Seite 31).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from stockagent.core import registry
from stockagent.core.calc import Eingabe, Ergebnis
from stockagent.core.reihen import Reihen, Split

ROOT = Path(__file__).resolve().parents[2]
T25, T24, T23 = date(2025, 9, 27), date(2024, 9, 28), date(2023, 9, 30)
T22, T21, T20 = date(2022, 9, 24), date(2021, 9, 25), date(2020, 9, 26)
START = {
    T25: date(2024, 9, 29),
    T24: date(2023, 10, 1),
    T23: date(2022, 9, 25),
    T22: date(2021, 9, 26),
    T21: date(2020, 9, 27),
    T20: date(2019, 9, 29),
}
VEROEFFENTLICHT = {
    "10-K 2025": datetime(2025, 10, 31, 14, 1, tzinfo=UTC),
    "10-K 2024": datetime(2024, 11, 1, 14, 0, tzinfo=UTC),
    "10-K 2022": datetime(2022, 10, 28, 14, 0, tzinfo=UTC),
}
MIO = Decimal(1_000_000)
TSD = Decimal(1_000)

# Bilanz (Stand), Mio. USD
STAND = {
    "total_assets": {
        T25: ("359241", 31),
        T24: ("364980", 31),
        T23: ("352583", 31),
        T22: ("352755", 31),
        T21: ("351002", 31),
    },
    "current_assets": {T25: ("147957", 31), T24: ("152987", 31), T23: ("143566", 31)},
    "current_liabilities": {T25: ("165631", 31), T24: ("176392", 31), T23: ("145308", 31)},
    "cash": {T25: ("35934", 31), T24: ("29943", 31)},
    "st_investments": {T25: ("18763", 31), T24: ("35228", 31)},
    "receivables": {T25: ("39777", 31), T24: ("33410", 31)},
    "inventory": {T25: ("5718", 31), T24: ("7286", 31)},
    "ppe_net": {T25: ("49834", 31), T24: ("45680", 31)},
    "lt_securities": {T25: ("77723", 31), T24: ("91479", 31)},
    "commercial_paper": {T25: ("7979", 31), T24: ("9967", 31)},
    "debt_current": {T25: ("12350", 31), T24: ("10912", 31)},
    "debt_noncurrent": {T25: ("78328", 31), T24: ("85750", 31)},
    "debt_long_total": {T25: ("90678", 31), T24: ("96662", 31)},
    "total_liabilities": {T25: ("285508", 31), T24: ("308030", 31)},
    "retained_earnings": {T25: ("-14264", 31), T24: ("-19154", 31)},
    "equity": {T25: ("73733", 31), T24: ("56950", 31), T23: ("62146", 31), T22: ("50672", 31)},
    # Leasing Seite 42: Operating kurz- plus langfristig, Finance kurz- plus langfristig
    "lease_operating": {T25: ("12490", 42), T24: ("11534", 42)},
    "lease_finance": {T25: ("1230", 42), T24: ("896", 42)},
}
# Ströme über das Geschäftsjahr, Mio. USD
STROM = {
    "revenue": {
        T25: ("416161", 29),
        T24: ("391035", 29),
        T23: ("383285", 29),
        T22: ("394328", 29),
        T21: ("365817", 29),
        T20: ("274515", 29),
    },
    "cost_of_revenue": {T25: ("220960", 29), T24: ("210352", 29), T23: ("214137", 29)},
    "gross_profit": {T25: ("195201", 29), T24: ("180683", 29), T23: ("169148", 29)},
    "ebit": {
        T25: ("133050", 29),
        T24: ("123216", 29),
        T23: ("114301", 29),
        T22: ("119437", 29),
        T21: ("108949", 29),
        T20: ("66288", 29),
    },
    "pretax_income": {T25: ("132729", 29), T24: ("123485", 29)},
    "income_tax": {T25: ("20719", 29), T24: ("29749", 29)},
    "net_income": {T25: ("112010", 29), T24: ("93736", 29), T23: ("96995", 29)},
    "sga": {T25: ("27601", 29), T24: ("26097", 29)},
    "depreciation": {T25: ("11698", 33), T24: ("11445", 33), T23: ("11519", 33)},
    "sbc": {T25: ("12863", 33), T24: ("11688", 33)},
    "operating_cash_flow": {
        T25: ("111482", 33),
        T24: ("118254", 33),
        T23: ("110543", 33),
        T22: ("122151", 33),
        T21: ("104038", 33),
        T20: ("80674", 33),
    },
    "capex": {T25: ("12715", 33), T24: ("9447", 33), T23: ("10959", 33), T20: ("7309", 33)},
    "dividends_paid": {T25: ("15421", 33), T24: ("15234", 33)},
    "buybacks": {T25: ("90711", 33), T24: ("94949", 33)},
    # Übernahmen 2022 und 2021 (10-K 2022, Seite 33). Ab 2023 keine eigene Zeile mehr
    "acquisitions": {T22: ("306", 33), T21: ("33", 33)},
}
EPS = {T25: ("7.46", 29), T24: ("6.08", 29), T20: ("3.28", 29)}
AKTIEN = {
    T25: ("15004697", 29),
    T24: ("15408095", 29),
    T23: ("15812547", 29),
    T22: ("16325819", 29),
    T20: ("17528214", 29),
}

# Schlusskurs in USD je Aktie (nach dem Split 2020) und tatsächlicher Handelstag
KURS = {
    T25: ("255.4600067138672", date(2025, 9, 26)),
    T24: ("227.7899932861328", date(2024, 9, 27)),
}


def _dokument(t: date) -> str:
    return "10-K 2025" if t >= T24 else ("10-K 2024" if t == T23 else "10-K 2022")


def _e(
    name: str, t: date, roh: str, seite: int, einheit: str, faktor: Decimal, strom: bool
) -> Eingabe:
    doc = _dokument(t)
    return Eingabe(
        Decimal(roh) * faktor,
        f"{doc} Seite {seite}: {name}",
        einheit,
        t,
        None if einheit == "shares" else "USD",
        START[t] if strom else None,
        VEROEFFENTLICHT[doc],
    )


def werte() -> dict[str, dict[date, Eingabe]]:
    out: dict[str, dict[date, Eingabe]] = {}
    for name, je in STAND.items():
        out[name] = {t: _e(name, t, v, s, "monetary", MIO, False) for t, (v, s) in je.items()}
    for name, je in STROM.items():
        out[name] = {t: _e(name, t, v, s, "monetary", MIO, True) for t, (v, s) in je.items()}
    out["eps_diluted"] = {
        t: _e("eps", t, v, s, "per_share", Decimal(1), True) for t, (v, s) in EPS.items()
    }
    out["shares_diluted"] = {
        t: _e("aktien", t, v, s, "shares", TSD, True) for t, (v, s) in AKTIEN.items()
    }
    for name, (je, einheit, quelle) in MARKT.items():
        out[name] = {t: Eingabe(Decimal(v), quelle, einheit, t) for t, v in je.items()}
    out["kurs"] = {
        t: Eingabe(Decimal(v), f"Yahoo AAPL Schlusskurs {tag.isoformat()}", "per_share", t, "USD")
        for t, (v, tag) in KURS.items()
    }
    return out


# Kapitalmarkt am Geschäftsjahresende (Lauf vom 19.10.2026, `stockagent markt update`):
# - rf: Treasury 10 Yr am letzten Handelstag vor dem Stichtag (home.treasury.gov, Daily Treasury
#   Par Yield Curve 2025 und 2024), in Prozent.
# - erp: Damodaran, ERPbymonth.xlsx, Spalte "ERP (T12m)", Monat des Stichtags.
# - beta_unverschuldet: Damodaran Betas.html Stand January 2026, Branche Computers/Peripherals
#   (Apple steht dort als NasdaqGS:AAPL), "Unlevered beta corrected for cash".
# - kd_branche: Damodaran wacc.html Stand January 2026, Cost of Debt der Branche, in Prozent.
# - rf_damodaran: Damodarans Treasury-Zins zum Stand der Tabelle (ERPbymonth.xlsx, 01.2026).
# - steuersatz, endwachstum_max: config/kapitalkosten.yaml.
MARKT = {
    "rf": ({T25: "4.20", T24: "3.75"}, "prozent", "Treasury 10 Yr {tag}"),
    "erp": (
        {T25: "0.039399999999999998", T24: "0.0406"},
        "anteil",
        "Damodaran ERP (T12m) Monat des Stichtags",
    ),
    "beta_unverschuldet": (
        {T25: "1.32", T24: "1.32"},
        "faktor",
        "Damodaran Betas Stand January 2026, Computers/Peripherals",
    ),
    "kd_branche": ({T25: "5.29", T24: "5.29"}, "prozent", "Damodaran wacc Stand January 2026"),
    "rf_damodaran": (
        {T25: "0.041799999999999997", T24: "0.041799999999999997"},
        "anteil",
        "Damodaran Treasury 01.2026",
    ),
    "steuersatz": ({T25: "0.21", T24: "0.21"}, "anteil", "config/kapitalkosten.yaml US"),
    "endwachstum_max": ({T25: "0.025", T24: "0.025"}, "anteil", "config/kapitalkosten.yaml"),
}
# Rating-Tabelle für große Nicht-Finanzfirmen, Damodaran ratings.html Stand January 2026
RATINGS = [
    ("-100000", "0.199999", "D2/D", "19.00"),
    ("0.2", "0.649999", "C2/C", "16.00"),
    ("0.65", "0.799999", "Ca2/CC", "12.61"),
    ("0.8", "1.249999", "Caa/CCC", "8.85"),
    ("1.25", "1.499999", "B3/B-", "5.09"),
    ("1.5", "1.749999", "B2/B", "3.21"),
    ("1.75", "1.999999", "B1/B+", "2.75"),
    ("2", "2.2499999", "Ba2/BB", "1.84"),
    ("2.25", "2.49999", "Ba1/BB+", "1.38"),
    ("2.5", "2.999999", "Baa2/BBB", "1.11"),
    ("3", "4.249999", "A3/A-", "0.89"),
    ("4.25", "5.499999", "A2/A", "0.78"),
    ("5.5", "6.499999", "A1/A+", "0.70"),
    ("6.5", "8.499999", "Aa2/AA", "0.55"),
    ("8.50", "100000", "Aaa/AAA", "0.40"),
]


def parameter() -> dict[str, Any]:
    kk = yaml.safe_load((ROOT / "config" / "kapitalkosten.yaml").read_text("utf-8"))
    return {
        "kapitalkosten": kk,
        "finanzfirma": False,
        "produzent": True,  # SIC 3571 Electronic Computers (SEC Submissions)
        "sic": 3571,
        "ratings": [
            {
                "art": "nichtfinanz",
                "ab": a,
                "bis": b,
                "rating": r,
                "aufschlag": s,
                "stand": "January 2026",
            }
            for a, b, r, s in RATINGS
        ],
        "vermerke_kapitalkosten": (),
    }


# Apple teilte die Aktie 2020 im Verhältnis 4:1. Alle Werte oben stammen aus Berichten nach dem
# Split und sind schon umgerechnet. Der Test der Bereinigung nutzt eigene Werte.
SPLIT_2020 = Split(datetime(2020, 10, 30, 14, 0, tzinfo=UTC), Decimal(4), "4:1")

APPLE = Reihen(
    "sec:0000320193",
    (T25, T24, T23, T22, T21, T20),
    werte(),
    (SPLIT_2020,),
    parameter=parameter(),
)

# Für das normalisierte EV/EBIT (mindestens 7 Jahre): operatives Ergebnis 2016 bis 2019 aus den
# SEC Company Facts, us-gaap:OperatingIncomeLoss, Geschäftsjahr wie angegeben, je aus dem 10-K des
# Jahres (Accession in der Quelle).
T19, T18, T17, T16 = date(2019, 9, 28), date(2018, 9, 29), date(2017, 9, 30), date(2016, 9, 24)
EBIT_FRUEHER = {
    T19: ("63930", "0000320193-19-000119"),
    T18: ("70898", "0000320193-18-000145"),
    T17: ("61344", "0000320193-17-000070"),
    T16: ("60024", "0001628280-16-020309"),
}


def _zehn_jahre() -> Reihen:
    w = {k: dict(v) for k, v in APPLE.werte.items()}
    for t, (v, acc) in EBIT_FRUEHER.items():
        w["ebit"][t] = Eingabe(
            Decimal(v) * MIO,
            f"us-gaap:OperatingIncomeLoss FY bis {t.isoformat()} (Accession {acc})",
            "monetary",
            t,
            "USD",
        )
    return Reihen(
        APPLE.subjekt,
        (*APPLE.stichtage, T19, T18, T17, T16),
        w,
        APPLE.splits,
        parameter=APPLE.parameter,
    )


APPLE_10J = _zehn_jahre()


def definition(metric_id: str) -> dict[str, Any]:
    cfg = yaml.safe_load((ROOT / "config" / "metrics.yaml").read_text("utf-8"))
    return next(m for m in cfg["metrics"] if m["id"] == metric_id)


def rechne(metric_id: str, reihen: Reihen = APPLE, t: date = T25) -> Ergebnis:
    return registry.berechne(definition(metric_id), reihen, t)


def schritt(erg: Ergebnis, name: str) -> Decimal:
    for s in erg.rechenweg["schritte"]:
        if s["name"] == name:
            return Decimal(s["ergebnis"])
    raise KeyError(f"Schritt {name} fehlt im Rechenweg")


def ohne(name: str, t: date | None = None, reihen: Reihen = APPLE) -> Reihen:
    """Dieselben Reihen ohne eine Eingabe (ganz oder für ein Jahr)."""
    w = {k: dict(v) for k, v in reihen.werte.items()}
    if t is None:
        w.pop(name, None)
    else:
        w.get(name, {}).pop(t, None)
    return Reihen(
        reihen.subjekt, reihen.stichtage, w, reihen.splits, reihen.luecken, reihen.parameter
    )


def mit(name: str, t: date, wert: Decimal, reihen: Reihen = APPLE) -> Reihen:
    """Dieselben Reihen mit einem geänderten Wert."""
    w = {k: dict(v) for k, v in reihen.werte.items()}
    alt = w[name][t]
    w[name][t] = Eingabe(
        wert,
        alt.quelle,
        alt.einheit,
        alt.periode_ende,
        alt.waehrung,
        alt.periode_start,
        alt.veroeffentlicht,
    )
    return Reihen(
        reihen.subjekt, reihen.stichtage, w, reihen.splits, reihen.luecken, reihen.parameter
    )


def q(x: Decimal, stellen: int = 6) -> Decimal:
    return x.quantize(Decimal(1).scaleb(-stellen))
