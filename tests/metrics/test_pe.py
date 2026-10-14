"""pe: Handrechnung aus Apples 10-K und dem Schlusskurs bei Yahoo.

Quellen und Seiten in tests/metrics/apple.py.

Schlusskurs 255,4600067138672 USD / verwässerter Gewinn je Aktie 7,46 USD (S. 29) = 34,2440.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401


def test_pe_hand_calculation() -> None:
    erg = rechne("pe")
    assert erg.wert is not None, erg.grund
    assert q(erg.wert, 4) == Decimal("34.2440")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_pe_loss_is_not_defined_not_a_data_error() -> None:
    erg = rechne("pe", mit("eps_diluted", T25, Decimal("-1.20")))
    assert erg.unknown and erg.ungereimtheit is None
    assert erg.grund is not None and "positivem Gewinn" in erg.grund
