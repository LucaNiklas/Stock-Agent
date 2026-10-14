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
    assert any(
        s["name"] == "steigung_2023-09-30_2025-09-27" for s in tr["steigung"].rechenweg["schritte"]
    )
    # Niveau: Median 383.285, MAD 11.043, z = 0,6745 * 32.876 / 11.043 = 2,008.
    # Trend der Vorjahre 2020 bis 2024: Theil-Sen-Steigung 18.622,5, Gerade im Stichtagsjahr
    # bei 420.530, MAD der Abweichungen 19.777, z = 0,6745 * (416.161 - 420.530) / 19.777.
    # Wert ist der kleinere Betrag: -0,149006
    assert q(tr["plausibilitaet"].wert) == Decimal("-0.149006")
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


def test_52_53_week_years_count_as_separate_years() -> None:
    """Johnson & Johnson: Jahresenden 1.1.2023 und 31.12.2023 sind zwei Geschäftsjahre."""
    assert trends.geschaeftsjahr(date(2025, 12, 28), date(2023, 1, 1)) == -3
    assert trends.geschaeftsjahr(date(2025, 12, 28), date(2023, 12, 31)) == -2
    assert trends.geschaeftsjahr(date(2026, 1, 31), date(2025, 2, 1)) == -1


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


def _jetzt(wert: str | None) -> Ergebnis:
    return Ergebnis(
        "pe", Decimal(wert) if wert else None, "Kurs fehlt" if not wert else None, None, (), {}
    )


def test_percentile_against_own_history() -> None:
    """Umsatzreihe als Beispiel: höchstens 383.285 sind 274.515, 365.817 und 383.285, also 3 von
    6 Jahren = 0,5."""
    erg = trends.perzentil_historie(
        definition("pe"), "sec:test", _jahre(UMSATZ), _jetzt("383285"), T25, CFG
    )
    assert erg.wert == Decimal("0.5")
    assert [s["ergebnis"] for s in erg.rechenweg["schritte"]][:6] == ["1", "1", "0", "1", "0", "0"]
    hoch = trends.perzentil_historie(
        definition("pe"), "sec:test", _jahre(UMSATZ), _jetzt("999999"), T25, CFG
    )
    assert hoch.wert == 1


def test_percentile_needs_minimum_years_and_current_value() -> None:
    kurz = {t: w for t, w in UMSATZ.items() if t >= T23}
    erg = trends.perzentil_historie(
        definition("pe"), "sec:test", _jahre(kurz), _jetzt("1"), T25, CFG
    )
    assert erg.unknown and erg.ungereimtheit is None and "mindestens 5" in str(erg.grund)
    ohne = trends.perzentil_historie(
        definition("pe"), "sec:test", _jahre(UMSATZ), _jetzt(None), T25, CFG
    )
    assert ohne.unknown and ohne.ungereimtheit is None


def test_no_outlier_check_for_market_prices() -> None:
    """Ein Börsenwert, der sich verdoppelt, ist eine Marktbewegung, kein Datenfehler (CP-05)."""
    sprung = {**UMSATZ, T25: "900000"}
    assert "plausibilitaet" in _trend(sprung, "fcf")
    assert "plausibilitaet" not in _trend(sprung, "market_cap")


def test_percentile_not_defined_for_constant_series() -> None:
    """Keine Dividende in 6 Jahren und heute: Rang wäre 100 %, sagt aber nichts."""
    null = {t: "0" for t in UMSATZ}
    erg = trends.perzentil_historie(
        definition("pe"), "sec:test", _jahre(null), _jetzt("0"), T25, CFG
    )
    assert erg.unknown and erg.ungereimtheit is None and "gleich" in str(erg.grund)
