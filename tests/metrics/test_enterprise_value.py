"""enterprise_value: Handrechnung aus Apples 10-K und dem Schlusskurs bei Yahoo.

Quellen und Seiten in tests/metrics/apple.py.

Börsenwert 3.833.099.996.359,54 (siehe test_market_cap) + Nettoverschuldung 57.680 Mio.
(siehe test_net_debt) - Pensionsdefizit 0 + Minderheiten 0 - at-equity-Beteiligungen 0
= 3.890.779.996.359,54 USD. Brücke zurück: 3.890.779.996.359,54 - 57.680 Mio. = Börsenwert.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from tests.metrics.apple import APPLE, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401


def test_enterprise_value_hand_calculation() -> None:
    erg = rechne("enterprise_value")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "nettoverschuldung") == Decimal("57680000000")
    assert schritt(erg, "minderheitsanteile_nicht_gemeldet") == 0
    assert q(schritt(erg, "bruecke_zum_boersenwert"), 2) == Decimal("3833099996359.54")
    assert q(erg.wert, 2) == Decimal("3890779996359.54")
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_enterprise_value_with_minorities_and_investments() -> None:
    """Gesetzte Werte: Minderheiten 1.000 Mio. (Eigenkapital gesamt 74.733 minus 73.733),
    Beteiligungen 500 Mio.: 3.890.779.996.359,54 + 1.000 Mio. - 500 Mio."""
    w = {k: dict(v) for k, v in APPLE.werte.items()}
    ek = w["equity"][T25]
    w["equity_incl_nci"] = {T25: replace(ek, wert=Decimal("74733000000"), quelle="Testwert")}
    w["equity_investments"] = {T25: replace(ek, wert=Decimal("500000000"), quelle="Testwert")}
    erg = rechne("enterprise_value", replace(APPLE, werte=w))
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "minderheitsanteile") == Decimal("1000000000")
    assert q(erg.wert, 2) == Decimal("3891279996359.54")
