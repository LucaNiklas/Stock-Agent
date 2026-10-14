"""piotroski_f_score: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

9 Signale 2025 gegen 2024: ROA 112.010 / 364.980 > 0 (1), CFO 111.482 / 364.980 > 0 (1), ROA
gestiegen gegen 93.736 / 352.583 (1), CFO 0,305447 nicht größer als ROA 0,306893 (0), Hebel
78.328 / 362.110,5 = 0,216309 gegen 85.750 / 358.781,5 = 0,239003 gesunken (1), Current Ratio
0,893293 gegen 0,867307 gestiegen (1), Aktien 15.004.697 <= 15.408.095 (1), Bruttomarge 0,469052
gegen 0,462061 gestiegen (1), Umschlag 1,140230 gegen 1,109056 gestiegen (1). Summe 8.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_piotroski_f_score_hand_calculation() -> None:
    erg = rechne("piotroski_f_score")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "punkt_cfo_groesser_roa") == Decimal("0")
    assert schritt(erg, "punkt_hebel_gesunken") == Decimal("1")
    assert erg.wert == Decimal("8")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_piotroski_f_score_failed_checkpoint_stops() -> None:
    erg = rechne("piotroski_f_score", mit("total_assets", T24, Decimal(0)))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_piotroski_f_score_missing_input_is_unknown() -> None:
    erg = rechne("piotroski_f_score", ohne("current_assets"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "current_assets" in erg.grund
