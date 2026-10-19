"""TTM-Werte aus Quartalsberichten (core/ttm.py, SPEC 3.4 Nr. 1).

Apple, Quartal bis 27.06.2026 (10-Q, Accession 0000320193-26-000020), Werte der SEC Company Facts:
Umsatz GJ 2025 416.161 + 9 Monate 2026 364.357 - 9 Monate 2025 313.695 = 466.823 Mio. USD.
Operativer Cashflow 111.482 + 116.996 - 81.754 = 146.724 Mio. USD.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from stockagent.core import ttm
from stockagent.core.calc import Eingabe
from tests.metrics.apple import APPLE, T25

Q = date(2026, 6, 27)
MIO = Decimal(1_000_000)


def _e(wert: str, start: date, ende: date, quelle: str) -> Eingabe:
    return Eingabe(Decimal(wert) * MIO, quelle, "monetary", ende, "USD", start)


UMSATZ = ttm.Strom(
    _e("416161", date(2024, 9, 29), T25, "10-K 2025"),
    _e("364357", date(2025, 9, 28), Q, "10-Q Q3 2026"),
    _e("313695", date(2024, 9, 29), date(2025, 6, 28), "10-Q Q3 2026 Vorjahr"),
)
OCF = ttm.Strom(
    _e("111482", date(2024, 9, 29), T25, "10-K 2025"),
    _e("116996", date(2025, 9, 28), Q, "10-Q Q3 2026"),
    _e("81754", date(2024, 9, 29), date(2025, 6, 28), "10-Q Q3 2026 Vorjahr"),
)


def test_ttm_hand_calculation() -> None:
    kasse = Eingabe(Decimal(39544) * MIO, "10-Q Q3 2026", "monetary", Q, "USD")
    erg = ttm.ttm_werte(
        "sec:0000320193", Q, {"revenue": UMSATZ, "operating_cash_flow": OCF}, {"cash": kasse}
    )
    assert erg.werte["revenue"].wert == Decimal("466823") * MIO
    assert erg.werte["operating_cash_flow"].wert == Decimal("146724") * MIO
    assert erg.werte["revenue"].periode_ende == Q
    assert "9 Monate" in erg.werte["revenue"].quelle
    assert erg.werte["cash"].wert == Decimal(39544) * MIO and not erg.luecken


def test_ttm_rejects_mismatched_periods() -> None:
    falsch = replace(UMSATZ, ytd_vj=_e("90000", date(2025, 3, 30), date(2025, 6, 28), "3 Monate"))
    erg = ttm.ttm_werte("x", Q, {"revenue": falsch}, {})
    assert "revenue" not in erg.werte and "CP-02" in erg.luecken["revenue"]
    andere = replace(UMSATZ, ytd=replace(UMSATZ.ytd, waehrung="EUR"))
    erg = ttm.ttm_werte("x", Q, {"revenue": andere}, {})
    assert "CP-01" in erg.luecken["revenue"]


def test_ttm_reihen_puts_quarter_first() -> None:
    erg = ttm.ttm_werte("x", Q, {"revenue": UMSATZ}, {})
    r = ttm.ttm_reihen(APPLE, Q, erg)
    assert r.stichtage[:2] == (Q, T25)
    assert r.hole("revenue", Q).wert == Decimal("466823") * MIO
    assert r.hole("beta_unverschuldet", Q).wert == Decimal("1.32"), "Annahmen übernommen"
