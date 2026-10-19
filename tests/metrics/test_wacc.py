"""wacc: Handrechnung aus Apples 10-K, Yahoo-Kurs, Treasury-Zins und Damodaran-Daten.

Quellen in tests/metrics/apple.py (MARKT, RATINGS).

Abschnitt 1, Eigenkapitalkosten:
- rf = 4,20 % / 100 = 0,042 (Treasury 10 Yr, 26.09.2025)
- EK = Börsenwert 3.833.099.996.359,54 (siehe test_market_cap)
- FK = Finanzschulden 98.657 + Leasing 13.720 = 112.377 Mio. (siehe test_net_debt)
- Beta verschuldet = 1,32 * (1 + 0,79 * 112.377 Mio. / 3.833.099.996.359,54)
  = 1,32 * 1,0231608 = 1,350572
- Eigenkapitalkosten = 0,042 + 1,350572 * 0,0394 = 0,095213
Abschnitt 2, Fremdkapitalkosten: Apple meldet keinen Zinsaufwand, also Aufschlag der Branche
Computers/Peripherals: 5,29 % - 4,18 % = 1,11 %. Fremdkapitalkosten 0,042 + 0,0111 = 0,0531,
nach Steuern 0,0531 * 0,79 = 0,041949.
Abschnitt 3: Gewichte EK 0,971518 und FK 0,028482, WACC = 0,971518 * 0,095213 + 0,028482 *
0,041949 = 0,093695, also 9,37 %.
"""

from __future__ import annotations

from decimal import Decimal

from tests.metrics.apple import APPLE, APPLE_10J, T24, T25, mit, ohne, q, rechne, schritt  # noqa: F401
from tests.metrics.helpers import mit_zinsen


def test_wacc_hand_calculation() -> None:
    erg = rechne("wacc")
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "fremdkapital") == Decimal("112377000000")
    assert q(schritt(erg, "beta_verschuldet")) == Decimal("1.350572")
    assert q(schritt(erg, "eigenkapitalkosten")) == Decimal("0.095213")
    assert q(schritt(erg, "aufschlag_branche")) == Decimal("0.011100")
    assert q(schritt(erg, "fremdkapitalkosten_nach_steuern")) == Decimal("0.041949")
    assert q(erg.wert) == Decimal("0.093695")
    assert any(v.startswith("KD_BRANCHE") for v in erg.vermerke)
    assert all(p["bestanden"] for p in erg.rechenweg["pruefungen"])


def test_wacc_with_interest_uses_synthetic_rating() -> None:
    """Gesetzter Zinsaufwand 2.000 Mio.: Zinsdeckung 133.050 / 2.000 = 66,5 -> Aaa/AAA, Aufschlag
    0,40 %. Fremdkapitalkosten 0,046, nach Steuern 0,03634. WACC = 0,971518 * 0,095213 +
    0,028482 * 0,03634 = 0,093536."""
    erg = rechne("wacc", mit_zinsen(Decimal("2000000000")))
    assert erg.wert is not None, erg.grund
    assert schritt(erg, "zinsdeckung") == Decimal("66.525")
    assert schritt(erg, "aufschlag") == Decimal("0.004")
    assert q(erg.wert) == Decimal("0.093536")


def test_wacc_without_rate_is_unknown() -> None:
    erg = rechne("wacc", ohne("rf"))
    assert erg.unknown and erg.ungereimtheit is None and "rf" in str(erg.grund)


def test_wacc_absurd_beta_stops() -> None:
    erg = rechne("wacc", mit("beta_unverschuldet", T25, Decimal("7")))
    assert erg.unknown and erg.ungereimtheit == "INC-15"
