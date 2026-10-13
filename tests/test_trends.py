"""Trends je Kennzahl (SPEC 3.4) mit Handrechnung.

Reihe: Apple-Umsatz in Mio. USD, GuV-Seite 29 der 10-K 2025 und 2022 (siehe
tests/metrics/apple.py). Die Vergleichswerte sind unabhängig mit Pythons `statistics` und einer
eigenen Schleife über alle Paare gerechnet.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import yaml

from stockagent.core import trends
from stockagent.core.calc import Ergebnis
from tests.metrics.apple import APPLE, ROOT, T22, T23, T24, T25, definition, q

CFG = yaml.safe_load((ROOT / "config" / "metrics.yaml").read_text("utf-8"))["trends"]
AUSREISSER = yaml.safe_load((ROOT / "config" / "quality.yaml").read_text("utf-8"))["ausreisser"]
UMSATZ = {
    date(2020, 9, 26): "274515",
    date(2021, 9, 25): "365817",
    T22: "394328",
    T23: "383285",
    T24: "391035",
    T25: "416161",
}


def _jahre(werte: dict[date, str]) -> dict[date, Ergebnis]:
    return {t: Ergebnis("fcf", Decimal(w), None, None, (), {}) for t, w in werte.items()}


def _trend(werte: dict[date, str] = UMSATZ, metric_id: str = "fcf", t: date = T25) -> Any:
    return trends.trend(definition(metric_id), "sec:test", _jahre(werte), t, "USD", CFG, AUSREISSER)


def test_trend_hand_calculation() -> None:
    tr = _trend()
    assert tr["niveau"].wert == Decimal("416161")
    # (416161 - 391035) / 391035 = 25126 / 391035
    assert q(tr["veraenderung_vj"].wert) == Decimal("0.064255")
    # (416161 / 394328) ^ (1/3) - 1 und (416161 / 274515) ^ (1/5) - 1, wie revenue_cagr_*
    assert q(tr["cagr_3j"].wert) == Decimal("0.018125")
    assert q(tr["cagr_5j"].wert) == Decimal("0.086774")
    # Mittelwert 370856,83, Stichprobenstreuung 49944,228
    assert q(tr["stdabw"].wert, 3) == Decimal("49944.228")
    # 15 Paare, Median der sortierten Steigungen ist die 8.: (416161 - 383285) / 2 = 16438
    assert tr["steigung"].wert == Decimal("16438")
    assert any(s["name"] == "steigung_2023_2025" for s in tr["steigung"].rechenweg["schritte"])
    # Vorjahre 274515 .. 391035: Median 383285, MAD 11043, z = 0,6745 * 32876 / 11043
    assert q(tr["plausibilitaet"].wert) == Decimal("2.008047")
    assert not tr["plausibilitaet"].warnungen


def test_ratio_change_in_points() -> None:
    tr = _trend({T24: "0.30", T25: "0.32"}, metric_id="ebit_margin")
    assert tr["veraenderung_vj"].wert == Decimal("0.02")
    assert tr["stdabw"].unknown and "mindestens 5" in str(tr["stdabw"].grund)
    assert "plausibilitaet" not in tr


def test_outlier_is_warning_not_stop() -> None:
    tr = _trend({**UMSATZ, T25: "1416161"})
    assert tr["plausibilitaet"].wert is not None and tr["plausibilitaet"].warnungen


def test_negative_start_gives_unknown_cagr() -> None:
    tr = _trend({**UMSATZ, T22: "-5"})
    assert tr["cagr_3j"].unknown and tr["cagr_3j"].ungereimtheit is None
    assert str(tr["cagr_3j"].grund).startswith("Nicht definiert")
    assert tr["cagr_5j"].wert is not None


def test_missing_stichtag_year_gives_unknown_level() -> None:
    werte = {t: w for t, w in UMSATZ.items() if t != T25}
    tr = _trend(werte)
    assert tr["niveau"].unknown and tr["veraenderung_vj"].unknown
    assert tr["niveau"].ungereimtheit is None
    assert "plausibilitaet" not in tr


def test_gap_year_gives_no_change() -> None:
    werte = {t: w for t, w in UMSATZ.items() if t != T24}
    erg = _trend(werte)["veraenderung_vj"]
    assert erg.unknown and erg.ungereimtheit is None and "Vorjahr" in str(erg.grund)


def test_same_fiscal_year_twice_stops() -> None:
    """Zwei Stichtage im selben Kalenderjahr (Wechsel des Geschäftsjahres): CP-01 stoppt."""
    werte = {**UMSATZ, date(2025, 1, 31): "100000"}
    assert str(_trend(werte)["stdabw"].grund).startswith("CP-01")


def test_vertical_analysis() -> None:
    v = trends.vertikal(APPLE, T25)
    # 220960 / 416161 (GuV Seite 29) und 35934 / 359241 (Bilanz Seite 31)
    assert q(v["cost_of_revenue"].wert) == Decimal("0.530948")
    assert q(v["cash"].wert) == Decimal("0.100028")
    assert "revenue" not in v and "shares_diluted" not in v


def test_series_over_years() -> None:
    jahre = trends.jahresreihe(definition("gross_margin"), APPLE, 10)
    assert q(jahre[T25].wert) == Decimal("0.469052")
    assert jahre[T22].unknown  # Umsatzkosten 2022 nicht in den Testwerten
