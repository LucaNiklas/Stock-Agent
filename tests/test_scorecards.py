"""Bauschritt 8: Kennzahlen der Branchen-Scorecards mit Handrechnung aus echten Berichten.

Werte aus den 10-K-Berichten für 2025 (Company Facts der SEC, Abruf 20.10.2026):

JPMorgan Chase (CIK 19617), Mio. USD:
- Ergebnis der Stammaktionäre 55.681. Eigenkapital 362.438 (2025) und 344.758 (2024),
  Vorzugskapital 20.045 und 20.050, Geschäftswert 52.731 und 52.565 (übrige immaterielle Werte
  ohne Dimension nicht gemeldet: 0 mit Vermerk).
  Materielles Eigenkapital 2025 = 362.438 - 20.045 - 52.731 = 289.662,
  2024 = 344.758 - 20.050 - 52.565 = 272.143, Durchschnitt 280.902,5.
  ROTE = 55.681 / 280.902,5 = 19,82 % (JPMorgan meldet für 2025 rund 20 %).
- Kosten-Ertrags-Verhältnis = 95.640 / (95.443 + 87.004) = 52,42 % (gemeldet 52 %).
- Risikovorsorge 14.212, Kredite 1.408.905 und 1.299.590, Durchschnitt 1.354.247,5:
  Risikokosten 1,049 %. Nettoausbuchungen 9.849: Ausfallquote 0,727 %.
- Einlagen 2.559.320 / Verbindlichkeiten 4.062.462 = 63,00 %.
- TCE-Quote = 289.662 / (4.424.900 - 52.731) = 6,625 %.

Progressive (CIK 80661), Mio. USD: Schäden 53.959 / Prämien 81.661 = 66,08 %, Abwicklung
Vorjahre -1.394 / 81.661 = -1,707 %, Kapitalanlageergebnis 3.549 / Durchschnitt der Anlagen
(80.250 + 97.373) / 2 = 88.811,5 -> 3,996 %.

Realty Income (CIK 726728), Mio. USD: FFO = 1.058,590 + 2.524,200 + 471,335 - 177,640
= 3.876,485, je Aktie / 908,334 Mio. = 4,268 USD, Ausschüttung 2.920,895 / 3.876,485 = 75,35 %.

Southern Company (CIK 92122): Dividendendeckung 4.341 / 3.015 = 1,440.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import yaml

from stockagent.core import registry
from stockagent.core.calc import Eingabe
from stockagent.core.reihen import Reihen
from tests.sec_fixtures import ROOT

METRICS = {
    m["id"]: m for m in yaml.safe_load((ROOT / "config/metrics.yaml").read_text("utf-8"))["metrics"]
}
T, V = date(2025, 12, 31), date(2024, 12, 31)
MIO = Decimal(1_000_000)


def _g(
    wert: str, konzept: str, t: date = T, einheit: str = "monetary", fluss: bool = False
) -> Eingabe:
    start = date(t.year, 1, 1) if fluss else None
    return Eingabe(Decimal(wert) * MIO, f"us-gaap:{konzept}", einheit, t, "USD", start)


def _reihen(werte: dict[str, dict[date, Eingabe]], **parameter: Any) -> Reihen:
    return Reihen("test", (T, V), werte, parameter=parameter)


def _wert(metric_id: str, d: Reihen) -> Decimal:
    e = registry.berechne(METRICS[metric_id], d, T)
    assert e.wert is not None, (metric_id, e.grund, e.ungereimtheit)
    return e.wert


JPM = {
    "net_income_common": {
        T: _g("55681", "NetIncomeLossAvailableToCommonStockholdersBasic", fluss=True)
    },
    "equity": {T: _g("362438", "StockholdersEquity"), V: _g("344758", "StockholdersEquity", V)},
    "preferred_equity": {
        T: _g("20045", "PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount"),
        V: _g("20050", "PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount", V),
    },
    "goodwill": {T: _g("52731", "Goodwill"), V: _g("52565", "Goodwill", V)},
    "noninterest_expense": {T: _g("95640", "NoninterestExpense", fluss=True)},
    "net_interest_income": {T: _g("95443", "InterestIncomeExpenseNet", fluss=True)},
    "noninterest_income": {T: _g("87004", "NoninterestIncome", fluss=True)},
    "credit_provision": {T: _g("14212", "ProvisionForLoanLeaseAndOtherLosses", fluss=True)},
    "net_charge_offs": {
        T: _g(
            "9849",
            "FinancingReceivableExcludingAccruedInterestAllowanceForCreditLossWriteoffAfterRecovery",
            fluss=True,
        )
    },
    "loans": {
        T: _g("1408905", "FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLoss"),
        V: _g(
            "1299590", "FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLoss", V
        ),
    },
    "loan_allowance": {
        T: _g("25765", "FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest")
    },
    "deposits": {T: _g("2559320", "Deposits")},
    "total_liabilities": {T: _g("4062462", "Liabilities")},
    "total_assets": {T: _g("4424900", "Assets")},
    "shares_diluted": {
        T: Eingabe(
            Decimal("2781500000"),
            "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
            "shares",
            T,
            None,
            date(2025, 1, 1),
        )
    },
}


def test_bank_metrics_jpmorgan() -> None:
    d = _reihen(JPM)
    assert _wert("rote", d).quantize(Decimal("0.0001")) == Decimal("0.1982")
    assert _wert("cost_income_ratio", d).quantize(Decimal("0.0001")) == Decimal("0.5242")
    assert _wert("credit_cost_ratio", d).quantize(Decimal("0.00001")) == Decimal("0.01049")
    assert _wert("net_charge_off_ratio", d).quantize(Decimal("0.00001")) == Decimal("0.00727")
    assert _wert("allowance_to_loans", d).quantize(Decimal("0.00001")) == Decimal("0.01829")
    assert _wert("deposit_share", d).quantize(Decimal("0.0001")) == Decimal("0.6300")
    assert _wert("tce_ratio", d).quantize(Decimal("0.00001")) == Decimal("0.06625")
    # 289.662 Mio. / 2.781,5 Mio. Aktien = 104,14 USD je Aktie
    assert _wert("tangible_book_per_share", d).quantize(Decimal("0.01")) == Decimal("104.14")
    e = registry.berechne(METRICS["rote"], d, T)
    assert any(
        "intangibles_ex_goodwill_nicht_gemeldet" in s["name"] for s in e.rechenweg["schritte"]
    )


def test_bank_valuation_residual_income() -> None:
    """Testwerte für Kurs und Kapitalkosten (Formel, nicht Markt): Kurs 300 USD, rf 4,2 %,
    Risikoprämie 4,3 %, Branchenbeta 1,0 -> Eigenkapitalkosten 8,5 %. g = 0.
    P/TBV = 300 * 2.781,5 Mio. / 289.662 Mio. = 2,8808. Gerechtfertigt 0,19822 / 0,085 = 2,3320.
    Abstand 2,3320 / 2,8808 - 1 = -19,05 % (Kurs über dem gerechtfertigten Wert)."""
    werte = {
        **JPM,
        "kurs": {T: Eingabe(Decimal(300), "Testkurs", "per_share", T, "USD")},
        "rf": {T: Eingabe(Decimal("4.2"), "Testzins", "prozent", T)},
        "erp": {T: Eingabe(Decimal("0.043"), "Testprämie", "anteil", T)},
        "beta_branche": {T: Eingabe(Decimal(1), "Testbeta", "faktor", T)},
        "parameter_residualgewinn_wachstum": {
            T: Eingabe(Decimal(0), "config/metrics.yaml", "pure", T)
        },
    }
    d = _reihen(werte)
    assert _wert("p_tbv", d).quantize(Decimal("0.0001")) == Decimal("2.8808")
    assert _wert("p_tbv_gap", d).quantize(Decimal("0.0001")) == Decimal("-0.1905")


def test_insurer_metrics_progressive() -> None:
    d = _reihen(
        {
            "premiums_earned": {T: _g("81661", "PremiumsEarnedNet", fluss=True)},
            "claims_incurred": {
                T: _g("53959", "PolicyholderBenefitsAndClaimsIncurredNet", fluss=True)
            },
            "prior_year_development": {
                T: _g(
                    "-1394",
                    "SupplementalInformationForPropertyCasualtyInsuranceUnderwritersPriorYearClaimsAndClaimsAdjustmentExpense",
                    fluss=True,
                )
            },
            "net_investment_income": {T: _g("3549", "NetInvestmentIncome", fluss=True)},
            "investments": {T: _g("97373", "Investments"), V: _g("80250", "Investments", V)},
        }
    )
    assert _wert("loss_ratio", d).quantize(Decimal("0.0001")) == Decimal("0.6608")
    assert _wert("reserve_development", d).quantize(Decimal("0.00001")) == Decimal("-0.01707")
    assert _wert("investment_yield", d).quantize(Decimal("0.00001")) == Decimal("0.03996")


def test_reit_ffo_realty_income() -> None:
    d = _reihen(
        {
            "net_income_common": {
                T: _g("1058.590", "NetIncomeLossAvailableToCommonStockholdersBasic", fluss=True)
            },
            "depreciation": {T: _g("2524.200", "DepreciationDepletionAndAmortization", fluss=True)},
            "real_estate_impairment": {T: _g("471.335", "ImpairmentOfRealEstate", fluss=True)},
            "real_estate_gains": {T: _g("177.640", "GainLossOnSaleOfProperties", fluss=True)},
            "dividends_paid": {T: _g("2920.895", "PaymentsOfDividendsCommonStock", fluss=True)},
            "shares_diluted": {
                T: Eingabe(
                    Decimal("908334000"),
                    "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
                    "shares",
                    T,
                    None,
                    date(2025, 1, 1),
                )
            },
        }
    )
    assert _wert("ffo", d) == Decimal("3876485000")
    assert _wert("ffo_per_share", d).quantize(Decimal("0.001")) == Decimal("4.268")
    assert _wert("ffo_payout", d).quantize(Decimal("0.0001")) == Decimal("0.7535")
    e = registry.berechne(METRICS["ffo"], d, T)
    assert any("FFO_ANGENAEHERT" in v for v in e.vermerke)


def test_utility_dividend_cover_southern() -> None:
    d = _reihen(
        {
            "net_income": {T: _g("4341", "NetIncomeLoss", fluss=True)},
            "dividends_paid": {T: _g("3015", "PaymentsOfDividendsCommonStock", fluss=True)},
        }
    )
    assert _wert("dividend_cover", d).quantize(Decimal("0.001")) == Decimal("1.440")


def test_cash_runway_capped_without_burn() -> None:
    """Kasse 120, kurzfristige Wertpapiere 30, OCF -40, Investitionen 10: FCF -50, Abfluss je
    Monat 4,1667 -> 36 Monate. Mit positivem FCF die Höchstgrenze 120 aus der Konfiguration."""
    basis = {
        "cash": {T: _g("120", "CashAndCashEquivalentsAtCarryingValue")},
        "st_investments": {T: _g("30", "ShortTermInvestments")},
        "operating_cash_flow": {
            T: _g("-40", "NetCashProvidedByUsedInOperatingActivities", fluss=True)
        },
        "capex": {T: _g("10", "PaymentsToAcquirePropertyPlantAndEquipment", fluss=True)},
        "parameter_liquiditaet_hoechst_monate": {
            T: Eingabe(Decimal(120), "config/metrics.yaml", "pure", T)
        },
    }
    assert _wert("cash_runway_months", _reihen(basis)) == 36
    plus = {
        **basis,
        "operating_cash_flow": {
            T: _g("40", "NetCashProvidedByUsedInOperatingActivities", fluss=True)
        },
    }
    assert _wert("cash_runway_months", _reihen(plus)) == 120


# ---------------------------------------------------------------- Scorecards und Zuordnung

SCORECARDS = yaml.safe_load((ROOT / "config/scorecards.yaml").read_text("utf-8"))
SCORING = yaml.safe_load((ROOT / "config/scoring.yaml").read_text("utf-8"))


def test_scorecard_config_is_consistent() -> None:
    """Jede Kennzahl einer Scorecard steht im Formelregister, die Statistik gibt es, `aktuell`
    nur bei Kurskennzahlen. Jede Scorecard hat alle Säulen aus SPEC 6.2, Gewichte ergeben 1."""
    from stockagent.core import gscore, trends

    saeulen = set(SCORING["saeulen_gewichte"])
    for sid, sc in SCORECARDS["scorecards"].items():
        if "nicht_bewertbar" in sc:
            continue
        assert set(sc["saeulen"]) == saeulen, sid
        gewichte = sc.get("saeulen_gewichte", SCORING["saeulen_gewichte"])
        assert sum(Decimal(str(v)) for v in gewichte.values()) == 1, sid
        for kennzahlen in sc["saeulen"].values():
            for k in kennzahlen:
                assert k["richtung"] in ("hoch", "niedrig")
                if k["kennzahl"] == gscore.KENNZAHL[0]:
                    continue
                d = METRICS[k["kennzahl"]]
                assert k["statistik"] in ("wert", *trends.STATISTIKEN), (sid, k)
                if k["statistik"] == "aktuell":
                    assert d.get("kurs"), (sid, k)
        for m in sc.get("multiples", []):
            assert METRICS[m["kennzahl"]].get("kurs"), (sid, m)
    ziele = {r["scorecard"] for r in SCORECARDS["zuordnung"]}
    assert ziele == set(SCORECARDS["scorecards"])


def test_assignment_rules() -> None:
    from stockagent.core import sektoren

    assert sektoren.scorecard(6021, False, SCORECARDS).id == "banken"
    assert sektoren.scorecard(6331, False, SCORECARDS).id == "versicherer"
    assert sektoren.scorecard(6798, False, SCORECARDS).id == "immobilien"
    assert sektoren.scorecard(4911, False, SCORECARDS).id == "versorger"
    assert sektoren.scorecard(3674, False, SCORECARDS).id == "cyclicals"
    assert sektoren.scorecard(7372, True, SCORECARDS).id == "growth"
    assert sektoren.scorecard(7372, False, SCORECARDS, holding=True).id == "holdings"
    # SIC-Regeln vor Kennzahlregeln: eine Bank mit Verlust bleibt Bank
    assert sektoren.scorecard(6021, True, SCORECARDS, holding=True).id == "banken"
    assert sektoren.scorecard(7372, False, SCORECARDS).id == "standard"


def test_mohanram_g_score_against_group_median() -> None:
    """Gruppe aus 3 Firmen, Mediane: roa 0,00, ocf_to_assets 0,05, Streuung roa 0,04,
    Streuung Umsatzwachstum 0,20, F&E 0,10, Investitionen 0,03. Werbung fehlt allen.
    Firma A: über/über/unter/unter/über/über und OCF > Ergebnis -> 7 von 7 = 1.
    Firma C: 0 von 7 erfüllt."""
    from stockagent.core import gscore

    def f(roa: str, ocf: str, s_roa: str, s_wachstum: str, fe: str, capex: str, ocf_ni: str):
        return {
            ("roa", "wert"): Decimal(roa),
            ("ocf_to_assets", "wert"): Decimal(ocf),
            ("roa", "stdabw"): Decimal(s_roa),
            ("revenue_growth", "stdabw"): Decimal(s_wachstum),
            ("rd_to_assets", "wert"): Decimal(fe),
            ("capex_to_assets", "wert"): Decimal(capex),
            ("ocf_to_net_income", "wert"): Decimal(ocf_ni),
        }

    a = f("0.02", "0.10", "0.02", "0.10", "0.15", "0.05", "1.5")
    b = f("0.00", "0.05", "0.04", "0.20", "0.10", "0.03", "1.0")
    c = f("-0.10", "-0.05", "0.09", "0.40", "0.02", "0.01", "0.5")
    eigen, gruppe, weg = gscore.ergaenzen("a", "2025-12-31", a, [b, c])
    assert eigen[gscore.KENNZAHL] == 1
    assert gruppe[1][gscore.KENNZAHL] == 0
    # Firma B liegt überall auf dem Median (nicht darüber), OCF = Ergebnis: 0 von 7
    assert gruppe[0][gscore.KENNZAHL] == 0
    assert weg["mediane"]["roa_wert"] == "0.00"
    # Unter 4 Signalen kein Wert
    wenig = {("roa", "wert"): Decimal("0.1"), ("ocf_to_assets", "wert"): Decimal("0.1")}
    assert gscore.g_score("x", "2025-12-31", wenig, {("roa", "wert"): Decimal(0)})[0] is None


def test_multiples_discount_with_yield_metrics() -> None:
    """FFO-Rendite 8 % gegen Median 6 %: Kurs relativ 0,08 / 0,06 = 1,333 -> Abschlag 25 %."""
    from stockagent.core import vergleichsgruppe
    from stockagent.core.calc import Rechenweg

    gruppe = [{"ffo_yield": Decimal(v)} for v in ("0.04", "0.05", "0.06", "0.07", "0.08")]
    r = Rechenweg("t", "1", "x", "t")
    a = vergleichsgruppe.multiples_abschlag(
        r, {"ffo_yield": Decimal("0.08")}, gruppe, {"ffo_yield"}
    )
    assert a is not None and a.quantize(Decimal("0.0001")) == Decimal("0.2500")


def test_confidence_downgrade() -> None:
    from stockagent.core import note

    assert note.konfidenz_abschlag("K1", 1, "G-Score")[0] == "K2"
    assert note.konfidenz_abschlag("K4", 1, "G-Score")[0] == "K4"
    assert note.konfidenz_abschlag("K2", 0, "x") == ("K2", None)
