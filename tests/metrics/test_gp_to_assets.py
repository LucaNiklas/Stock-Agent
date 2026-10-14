"""gp_to_assets: Handrechnung aus Apples 10-K.

Quellen und Seiten in tests/metrics/apple.py.

Bruttoergebnis 195.201 (S. 29) / Bilanzsumme 359.241 (S. 31) = 0,543371.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T20, T21, T22, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen, verschiedene_waehrung  # noqa: F401


def test_gp_to_assets_hand_calculation() -> None:
    erg = rechne("gp_to_assets")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert) == Decimal("0.543371")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_gp_to_assets_failed_checkpoint_stops() -> None:
    erg = rechne("gp_to_assets", mit("total_assets", T25, Decimal(0)))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_gp_to_assets_missing_input_is_unknown() -> None:
    erg = rechne("gp_to_assets", ohne("total_assets"))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "total_assets" in erg.grund
