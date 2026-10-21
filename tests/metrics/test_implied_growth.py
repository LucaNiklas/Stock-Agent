"""implied_growth (Reverse-DCF): Handrechnung für Apple 2025.

Gegeben: Unternehmenswert 3.890.779.996.359,54 (siehe test_enterprise_value), WACC 0,093695
(siehe test_wacc), Endwachstum min(4,20 %, 2,5 %) = 2,5 %. Basis: FCFF = FCF 98.767 Mio., Apple
meldet keinen Zinsaufwand (Vermerk). Gesucht ist g, bei dem
sum_{j=1..10} 98.767 Mio. * (1 + g)^j / (1 + WACC)^j + Endwert / (1 + WACC)^10 den
Unternehmenswert ergibt. Ergebnis 15,50 % je Jahr. Die Gegenprobe unten rechnet den Barwert mit
diesem g unabhängig in einer eigenen Schleife nach.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, APPLE_10J, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401


def _barwert(basis: Decimal, g: Decimal, w: Decimal, g_end: Decimal) -> Decimal:
    summe, cf = Decimal(0), basis
    for j in range(1, 11):
        cf *= 1 + g
        summe += cf / (1 + w) ** j
    return summe + cf * (1 + g_end) / (w - g_end) / (1 + w) ** 10


def test_implied_growth_hand_calculation() -> None:
    erg = rechne("implied_growth")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "basis_cashflow") == Decimal("98767000000")
    assert schritt(erg, "endwachstum") == Decimal("0.025")
    assert q(erg.wert, 4) == Decimal("0.1550")
    wacc = schritt(erg, "wacc")
    nach = _barwert(Decimal("98767000000"), erg.wert, wacc, Decimal("0.025"))
    ev = Decimal("3890779996359.5430342384000")
    assert abs(nach - ev) / ev < Decimal("0.000001")
    assert q(schritt(erg, "rueckrechnung_endwert_anteil"), 3) == Decimal("0.653")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])
    assert any(v.startswith("FCFF_OHNE_ZINSEN") for v in erg.vermerke)


def test_negative_fcf_uses_revenue_and_own_margin() -> None:
    """Capex so hoch, dass der FCF 2025 negativ wird: Basis = Umsatz 2025 * Median der FCF-Margen
    2025 bis 2020 (Vermerk UMSATZBASIS). Nur Jahre mit Umsatz, operativem Cashflow und Capex."""
    erg = rechne("implied_growth", mit("capex", T25, Decimal("120000000000")))
    assert erg.wert is not None, erg.grund
    assert any(v.startswith("UMSATZBASIS") for v in erg.vermerke)
    assert schritt(erg, "zielmarge") > 0


def test_growth_beyond_search_range_is_not_defined() -> None:
    erg = rechne("implied_growth", mit("kurs", T25, Decimal("500000")))
    assert erg.unknown and erg.ungereimtheit is None
    assert "mehr als 100 %" in str(erg.grund)
