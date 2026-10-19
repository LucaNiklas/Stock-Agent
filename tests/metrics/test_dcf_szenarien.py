"""dcf_bear, dcf_base, dcf_bull: Handrechnung für Apple 2025.

Quellen in tests/metrics/apple.py. Stufen aus den Jahren 2025 bis 2020 (soweit vorhanden):

- Working-Capital-Quote = (UV - Kasse - Wertpapiere - (kurzfr. Verb. - kurzfr. Schulden - CP))
  / Umsatz:
  2025 (147.957 - 35.934 - 18.763 - (165.631 - 12.350 - 7.979)) / 416.161 = -0,125053,
  2024 (152.987 - 29.943 - 35.228 - (176.392 - 10.912 - 9.967)) / 391.035 = -0,173123,
  2023 (143.566 - 29.965 - 31.590 - (145.308 - 9.822 - 5.985)) / 383.285 = -0,123903.
  25. Perzentil -0,173123 + 0,5 * (-0,125053 + 0,173123) = -0,149088, Median -0,125053,
  75. Perzentil -0,124478.
- Wachstum: 3-Jahres-Wachstum 2025 (416.161 / 394.328)^(1/3) - 1 = 0,018125 (wie
  revenue_cagr_3y), 2024 (391.035 / 365.817)^(1/3) - 1 = 0,022470, 2023 (383.285 / 274.515)^(1/3)
  - 1 = 0,117683. Median 0,022470.
- Base: operative Quote = Marge 0,300551 * 0,79 - Investitionsquote (-0,001461) = 0,238896.
  Wachstum 0,022470 in den Jahren 1 bis 5, dann linear bis 2,5 % im Jahr 10.

Der Wert je Aktie wird unten in einer eigenen Schleife nachgerechnet (Umsatz Jahr für Jahr,
FCFF = Umsatz * k, Abzinsung mit dem WACC, Endwert mit k_end, Brücke über die Nettoverschuldung
57.680 Mio. und 15.004.697 Tsd. Aktien).
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from tests.metrics.apple import APPLE, T25, mit, q, rechne, schritt  # noqa: F401


def test_stufen_hand_calculation() -> None:
    erg = rechne("dcf_base")
    assert erg.wert is not None, erg.grund
    assert q(schritt(erg, "wachstum_3j_2025_09_27")) == Decimal("0.018125")
    assert q(schritt(erg, "stufe_wachstum_mittel")) == Decimal("0.022470")
    assert q(schritt(erg, "working_capital_2023_09_30")) == Decimal("-0.123903")
    assert q(schritt(erg, "stufe_working_capital_niedrig")) == Decimal("-0.149088")
    assert q(schritt(erg, "stufe_working_capital_mittel")) == Decimal("-0.125053")
    assert q(schritt(erg, "stufe_working_capital_hoch")) == Decimal("-0.124478")
    assert q(schritt(erg, "base_operative_quote")) == Decimal("0.238896")
    assert q(schritt(erg, "base_g_8")) == Decimal("0.023988")


def test_base_value_recomputed_independently() -> None:
    erg = rechne("dcf_base")
    assert erg.wert is not None
    op = schritt(erg, "base_operative_quote")
    wc = schritt(erg, "stufe_working_capital_mittel")
    g = schritt(erg, "stufe_wachstum_mittel")
    w, g_end = schritt(erg, "wacc"), Decimal("0.025")
    with localcontext() as ctx:
        ctx.prec = 40
        u_vor, summe = Decimal("416161000000"), Decimal(0)
        for j in range(1, 11):
            g_j = g if j < 6 else g - (g - g_end) * (j - 5) / 5
            u = u_vor * (1 + g_j)
            summe += (u * op - (u - u_vor) * wc) / (1 + w) ** j
            u_vor = u
        u_end = u_vor * (1 + g_end)
        endwert = (u_end * op - (u_end - u_vor) * wc) / (w - g_end)
        ev = summe + endwert / (1 + w) ** 10
        je_aktie = (ev - Decimal("57680000000")) / Decimal("15004697000")
    assert abs(je_aktie - erg.wert) < Decimal("1e-20")
    assert q(erg.wert, 2) == Decimal("94.82")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_scenarios_ordered_and_sensitivity() -> None:
    bear, base, bull = rechne("dcf_bear"), rechne("dcf_base"), rechne("dcf_bull")
    assert bear.wert is not None and base.wert is not None and bull.wert is not None
    assert bear.wert < base.wert < bull.wert
    assert abs(schritt(base, "sens_wacc_0_g_0") - base.wert) < Decimal("1e-20")
    # Höherer WACC ergibt niedrigeren Wert, höheres Endwachstum höheren (BAUPLAN Schritt 4)
    assert schritt(base, "sens_wacc_0.01_g_0") < base.wert < schritt(base, "sens_wacc_-0.01_g_0")
    assert schritt(base, "sens_wacc_0_g_-0.005") < base.wert < schritt(base, "sens_wacc_0_g_0.005")


def test_scenarios_need_three_years() -> None:
    from tests.metrics.apple import ohne

    erg = rechne("dcf_base", ohne("current_assets"))
    assert erg.unknown and "working_capital" in str(erg.grund)


def test_no_positive_operating_margin_is_not_defined() -> None:
    """Verlust in allen Jahren: Marge nach Steuern negativ, kein DCF (Wachstum ohne Gewinn)."""
    from dataclasses import replace

    w = {k: dict(v) for k, v in APPLE.werte.items()}
    w["ebit"] = {t: replace(e, wert=-abs(e.wert)) for t, e in w["ebit"].items()}
    erg = rechne("dcf_base", replace(APPLE, werte=w))
    assert erg.unknown and erg.ungereimtheit is None
    assert "nicht aussagekräftig" in str(erg.grund)
