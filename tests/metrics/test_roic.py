"""roic: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

Steuersatz 20.719 / 132.729 = 0,156100 (S. 29). NOPAT = 133.050 * (1 - 0,156100) = 112.281,0.
Investiertes Kapital 2025 = 73.733 + (90.678 + 7.979) + (12.490 + 1.230) - 35.934 = 150.176;
2024 = 56.950 + (96.662 + 9.967) + (11.534 + 896) - 29.943 = 146.066 (S. 31, 42). Durchschnitt
148.121. ROIC = 0,758035.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_roic_hand_calculation() -> None:
    erg = rechne("roic")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "investiertes_kapital_2025-09-27") == Decimal("150176000000")
    assert schritt(erg, "investiertes_kapital_2024-09-28") == Decimal("146066000000")
    assert schritt(erg, "investiertes_kapital_durchschnitt") == Decimal("148121000000")
    assert q(erg.wert) == Decimal("0.758035")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_roic_failed_checkpoint_stops() -> None:
    erg = rechne("roic", mit("debt_noncurrent", T25, Decimal("70000000000")))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-04")


def test_roic_missing_input_is_unknown() -> None:
    erg = rechne("roic", ohne("income_tax"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "income_tax" in erg.grund
