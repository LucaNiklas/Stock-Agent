"""beneish_m_score: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

DSRI 1,118692, GMI 0,985096, AQI 1,136747, SGI 1,064255, DEPI 1,053869, SGAI 0,993776, TATA
0,001470, LVGI 0,945510 aus S. 29, 31, 33 (2025 und 2024). M = -2,234164, unter -1,78: keine
Eskalation.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_beneish_m_score_hand_calculation() -> None:
    erg = rechne("beneish_m_score")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert) == Decimal("-2.234164")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_beneish_m_score_failed_checkpoint_stops() -> None:
    erg = rechne("beneish_m_score", mit("receivables", T24, Decimal(0)))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_beneish_m_score_missing_input_is_unknown() -> None:
    erg = rechne("beneish_m_score", ohne("receivables"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "receivables" in erg.grund
