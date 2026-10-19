"""altman_z (Produzenten): Handrechnung aus Apples 10-K 2025 (S. 29, 31) und dem Börsenwert.

Apple ist Produzent (SIC 3571). X1 = (147.957 - 165.631) / 359.241 = -0,049198,
X2 = -14.264 / 359.241 = -0,039706, X3 = 133.050 / 359.241 = 0,370364,
X4 = 3.833.099.996.359,54 / 285.508 Mio. = 13,425543, X5 = 416.161 / 359.241 = 1,158445.
Z = 1,2 * X1 + 1,4 * X2 + 3,3 * X3 + 0,6 * X4 + 1,0 * X5 = 10,3213.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from tests.metrics.apple import APPLE, APPLE_10J, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401


def test_altman_z_hand_calculation() -> None:
    erg = rechne("altman_z")
    assert erg.wert is not None, erg.grund
    assert q(schritt(erg, "x1")) == Decimal("-0.049198")
    assert q(schritt(erg, "x4")) == Decimal("13.425543")
    assert q(erg.wert, 4) == Decimal("10.3213")


def test_altman_z_only_for_producers() -> None:
    kein = replace(APPLE, parameter={**APPLE.parameter, "produzent": False})
    erg = rechne("altman_z", kein)
    assert erg.unknown and erg.ungereimtheit is None and "Produzenten" in str(erg.grund)
