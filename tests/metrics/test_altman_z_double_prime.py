"""altman_z_double_prime: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

X1 = (147.957 - 165.631) / 359.241 = -0,049198; X2 = -14.264 / 359.241 = -0,039706; X3 = 133.050
/ 359.241 = 0,370364; X4 = 73.733 / 285.508 = 0,258254 (S. 29, 31). Z'' = 2,307831.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_altman_z_double_prime_hand_calculation() -> None:
    erg = rechne("altman_z_double_prime")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert) == Decimal("2.307831")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_altman_z_double_prime_failed_checkpoint_stops() -> None:
    erg = rechne("altman_z_double_prime", mit("total_assets", T25, Decimal(0)))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_altman_z_double_prime_missing_input_is_unknown() -> None:
    erg = rechne("altman_z_double_prime", ohne("retained_earnings"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "retained_earnings" in erg.grund
