"""Bauschritt 7: IFRS-Berichte (20-F bei der SEC), Hinterlegungsscheine und Leasing unter IFRS.

Zahlen aus den 20-F-Berichten für 2025 (Company Facts der SEC, Lauf vom 20.10.2026):
- Novartis meldet keinen Gesamtumsatz: Bruttoergebnis 42.975 + Umsatzkosten 13.699
  = 56.674 Mio. USD (RevenueFromSaleOfGoods 54.532 + OtherRevenue 2.142 = 56.674, gleich).
- SAP: ADR-Kurs 242,91 USD am 31.12.2025, 1 ADR = 1 Aktie, EZB 1,175 USD je EUR
  -> 242,91 / 1,175 = 206,73 EUR je Aktie.
- Shell: Gesamtschulden 75.643 Mio. USD enthalten 28.933 Mio. USD Leasing (20-F 2025 Seite 261),
  Nettoverschuldung laut Shell 45,7 Mrd. USD (Seite 37). Leasing darf nicht dazukommen.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from stockagent.core import abgeleitet, registry
from stockagent.core.calc import Eingabe, Rechenweg
from stockagent.core.identifiers import adr_verhaeltnis
from stockagent.core.reihen import Reihen
from stockagent.data import quality

T = date(2025, 12, 31)
T2026 = date(2026, 6, 30)


@pytest.mark.parametrize(
    ("name", "verhaeltnis"),
    [
        ("SAP SE ADR/1 O.N.", Decimal(1)),
        ("BP PLC SP.ADR/6 DL -,25", Decimal(6)),
        ("SANOFI SA ADR 1/2/EO 2", Decimal("0.5")),
        ("DIAGEO PLC ADR/4 LS -,25", Decimal(4)),
        ("GSK PLC SP. ADR/2 NEW", Decimal(2)),
        ("NOVARTIS NAM. ADR 1", Decimal(1)),
        ("NOVO-NORDISK B ADR/1DK 10", Decimal(1)),
        ("NOKIA OYJ A ADR 1/EO-,06", Decimal(1)),
        ("ARCELORMITTAL NY SHS/1 ON", Decimal(1)),
        ("KONINKL. PHILIPS ADR -,20", None),  # ohne Angabe: festlegen statt raten
        ("ERICSSON B (SPON.) ADR", None),
    ],
)
def test_adr_ratio_from_exchange_name(name: str, verhaeltnis: Decimal | None) -> None:
    assert adr_verhaeltnis(name) == verhaeltnis


def _e(wert: str, quelle: str, waehrung: str | None = None, einheit: str = "monetary") -> Eingabe:
    return Eingabe(Decimal(wert), quelle, einheit, T, waehrung, date(2025, 1, 1))


def test_adr_price_per_share_in_report_currency() -> None:
    d = Reihen(
        "sec:0001000184",
        (T,),
        {
            "revenue": {T: _e("36800000000", "ifrs-full:Revenue", "EUR")},
            "kurs": {T: Eingabe(Decimal("242.91"), "Yahoo SAP", "per_share", T, "USD")},
            "fx_USD": {T: Eingabe(Decimal("1.175"), "EZB", "pure", T)},
            "adr_aktien_je_schein": {T: Eingabe(Decimal(1), "Börsenname", "pure", T)},
        },
    )
    r = Rechenweg("t", "1", "x", "t")
    k = registry.marktkennzahlen.kurs(r, d, T)
    assert k.waehrung == "EUR" and k.wert.quantize(Decimal("0.01")) == Decimal("206.73")
    # BP-Fall: 1 ADR = 6 Aktien, der Kurs je Aktie ist ein Sechstel
    d6 = Reihen(
        d.subjekt,
        d.stichtage,
        {**d.werte, "adr_aktien_je_schein": {T: Eingabe(Decimal(6), "Börsenname", "pure", T)}},
    )
    k6 = registry.marktkennzahlen.kurs(Rechenweg("t", "1", "x", "t"), d6, T)
    assert (k6.wert * 6).quantize(Decimal("0.01")) == Decimal("206.73")


def test_revenue_derived_from_gross_profit_and_cost() -> None:
    brutto = {T: _e("42975000000", "ifrs-full:GrossProfit", "USD")}
    kosten = {T: _e("13699000000", "ifrs-full:CostOfSales", "USD")}
    out = abgeleitet.umsatz_aus_bruttoergebnis({}, brutto, kosten)
    assert out[T].wert == Decimal("56674000000") and out[T].quelle.startswith("abgeleitet")
    # Gemeldeter Umsatz bleibt, andere Währung wird nicht gemischt
    gemeldet = {T: _e("1", "ifrs-full:Revenue", "USD")}
    assert abgeleitet.umsatz_aus_bruttoergebnis(gemeldet, brutto, kosten)[T].wert == 1
    fremd = {T: _e("13699000000", "ifrs-full:CostOfSales", "EUR")}
    assert abgeleitet.umsatz_aus_bruttoergebnis({}, brutto, fremd) == {}


def test_ifrs_leases_inside_borrowings_are_not_added_twice() -> None:
    d = Reihen("sec:0001306965", (T,), {}, parameter={"leasing_in_finanzschulden": (T,)})
    r = Rechenweg("t", "1", "x", "t")
    assert registry.kennzahlen.leasing(r, d, T) == 0
    assert any("LEASING_IN_SCHULDEN" in v for v in r.vermerke)


def test_fiscal_year_needs_core_value() -> None:
    """Diageo: ein Planwert für das kommende Jahr im Anhang macht kein Geschäftsjahr."""

    def fakt(konzept: str, start: date, ende: date) -> SimpleNamespace:
        return SimpleNamespace(form="20-F", concept=konzept, period_start=start, period_end=ende)

    facts = [
        fakt("ifrs-full:Revenue", date(2024, 7, 1), date(2025, 6, 30)),
        fakt(
            "ifrs-full:EstimateOfContributionsExpectedToBePaidToPlan",
            date(2025, 7, 1),
            date(2026, 6, 30),
        ),
    ]
    assert quality.jahresstichtage(facts) == [date(2026, 6, 30), date(2025, 6, 30)]  # type: ignore[arg-type]
    kern = {"ifrs-full:Revenue"}
    assert quality.jahresstichtage(facts, kern) == [date(2025, 6, 30)]  # type: ignore[arg-type]


def test_gbx_price_in_pence_converted_to_pounds() -> None:
    """GBX-Fall (SPEC 5.2): Londoner Kurse in Pence, Bericht in Pfund. 2.450 GBp = 24,50 GBP.
    Mit Umrechnung in einen EUR-Bericht: 24,50 GBP / 0,85 GBP je EUR = 28,82 EUR."""
    werte = {
        "revenue": {T: _e("32667000000", "ifrs-full:Revenue", "GBP")},
        "kurs": {T: Eingabe(Decimal(2450), "Yahoo GSK.L", "per_share", T, "GBp")},
    }
    unter = {"unterwaehrungen": {"GBp": "GBP", "GBX": "GBP"}}
    d = Reihen("x", (T,), werte, parameter=unter)
    k = registry.marktkennzahlen.kurs(Rechenweg("t", "1", "x", "t"), d, T)
    assert k.waehrung == "GBP" and k.wert == Decimal("24.5")
    eur = {
        **werte,
        "revenue": {T: _e("1", "ifrs-full:Revenue", "EUR")},
        "fx_GBP": {T: Eingabe(Decimal("0.85"), "EZB", "pure", T)},
    }
    k2 = registry.marktkennzahlen.kurs(
        Rechenweg("t", "1", "x", "t"), Reihen("x", (T,), eur, parameter=unter), T
    )
    assert k2.waehrung == "EUR" and k2.wert.quantize(Decimal("0.01")) == Decimal("28.82")
