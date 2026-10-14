"""dividend_yield: Handrechnung aus Apples 10-K und dem Schlusskurs bei Yahoo.

Quellen und Seiten in tests/metrics/apple.py.

Gezahlte Dividenden 15.421 Mio. (S. 33) / Börsenwert 3.833.099.996.359,54
(siehe test_market_cap) = 0,004023, also 0,40 %.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import ohne_dividende_mit_yahoo


def test_dividend_yield_hand_calculation() -> None:
    erg = rechne("dividend_yield")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert) == Decimal("0.004023")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_dividend_yield_negative_dividends_stop() -> None:
    erg = rechne("dividend_yield", mit("dividends_paid", T25, Decimal("-1")))
    assert erg.unknown and erg.ungereimtheit == "INC-15"


def test_no_dividend_in_report_and_at_yahoo_counts_as_zero() -> None:
    """Gegenprobe (METHODOLOGY_CHANGELOG 4.7): kein Wert im Bericht, keine Dividende bei Yahoo."""
    erg = rechne("dividend_yield", ohne_dividende_mit_yahoo(0))
    assert erg.wert == 0, erg.grund
    assert schritt(erg, "dividenden_keine_laut_bericht_und_yahoo") == 0
    assert any(v.startswith("KEINE_DIVIDENDE") for v in erg.vermerke)


def test_dividend_at_yahoo_but_not_in_report_is_unknown_with_mapping_hint() -> None:
    """So wäre Johnson & Johnson aufgefallen: Yahoo zeigt 4 Dividenden, der Bericht keine Zeile."""
    erg = rechne("dividend_yield", ohne_dividende_mit_yahoo(4))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "Yahoo zeigt 4" in erg.grund
    assert "Zuordnung prüfen" in erg.grund


def test_no_dividend_and_no_yahoo_coverage_stays_unknown() -> None:
    erg = rechne("dividend_yield", ohne_dividende_mit_yahoo(None))
    assert erg.unknown and erg.grund is not None and "dividends_paid" in erg.grund
