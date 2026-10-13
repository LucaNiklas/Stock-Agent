"""SPEC 3.2: Arithmetik der Datenqualitätsprüfungen in core/dq.py, jeweils Handrechnung."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from stockagent.core import dq
from stockagent.core.calc import Eingabe

TOL = Decimal("0.005")


def usd(wert: str, ende: date = date(2025, 9, 27), start: date | None = None) -> Eingabe:
    return Eingabe(Decimal(wert), "test", "monetary", ende, "USD", start)


def shares(wert: str, ende: date) -> Eingabe:
    return Eingabe(Decimal(wert), "test", "shares", ende)


def test_balance_sheet_holds() -> None:
    # Handrechnung: |1000 - (600 + 399)| / 1000 = 0,001 <= 0,005
    erg = dq.bilanzgleichung("s", usd("1000"), [usd("600"), usd("399")], TOL)
    assert erg.wert == Decimal("0.001")


def test_balance_sheet_violated_stops() -> None:
    # |1000 - 980| / 1000 = 0,02 > 0,005
    erg = dq.bilanzgleichung("s", usd("1000"), [usd("980")], TOL)
    assert erg.unknown and erg.grund is not None and "CP-03" in erg.grund


def test_balance_sheet_needs_same_period() -> None:
    erg = dq.bilanzgleichung("s", usd("1000"), [usd("1000", ende=date(2024, 9, 28))], TOL)
    assert erg.unknown and erg.grund is not None and "CP-01" in erg.grund


def test_sum_check_with_weights_and_rounding() -> None:
    # Umsatz 100 = Produkte 70 + Dienste 31 (Rundung): Differenz 1, Grenze max(1, 0,5) = 1
    teile = [(usd("70"), Decimal(1)), (usd("31"), Decimal(1))]
    assert dq.summenprobe("s", "umsatz", usd("100"), teile, TOL, Decimal(1)).wert == 1
    # Bruttogewinn 40 = Umsatz 100 - Kosten 60 (Gewicht -1)
    teile = [(usd("100"), Decimal(1)), (usd("60"), Decimal(-1))]
    assert dq.summenprobe("s", "brutto", usd("40"), teile, TOL, Decimal(0)).wert == 0
    teile = [(usd("100"), Decimal(1)), (usd("50"), Decimal(-1))]
    assert dq.summenprobe("s", "brutto", usd("40"), teile, TOL, Decimal(1)).unknown


def test_reconciliation_thresholds() -> None:
    # 0,8 % Abweichung: in Ordnung. 2 %: Warnung. 6 %: Stopp (SPEC 3.2 Nr. 5)
    w, s = Decimal("0.01"), Decimal("0.05")
    ok = dq.abgleich("s", "umsatz", usd("1000"), usd("992"), w, s)
    assert ok.wert == Decimal("0.008") and not ok.warnungen
    warn = dq.abgleich("s", "umsatz", usd("1000"), usd("1020"), w, s)
    assert warn.wert == Decimal("0.02") and warn.warnungen
    assert dq.abgleich("s", "umsatz", usd("1000"), usd("1060"), w, s).unknown


def test_outlier_robust_z() -> None:
    hist = [usd(v, ende=date(2020 + i, 9, 30)) for i, v in enumerate(["10", "11", "12", "13"])]
    # Median 11,5, Abstände 1,5 0,5 0,5 1,5, MAD 1. z = 0,6745 * (20 - 11,5) / 1 = 5,73325
    erg = dq.ausreisser("s", "umsatz", hist, usd("20", ende=date(2025, 9, 30)), Decimal(4))
    assert erg is not None and erg.wert == Decimal("5.73325") and erg.warnungen
    assert dq.ausreisser("s", "umsatz", hist[:3], usd("20"), Decimal(4)) is None


def test_split_detection() -> None:
    a, b = date(2020, 6, 27), date(2020, 9, 26)
    # 4:1-Split mit leichter Veränderung: 1000 -> 4002, Verhältnis 4,002, Abstand 0,0005
    v = dq.split_verdacht("s", shares("1000", a), shares("4002", b), Decimal("0.02"))
    assert v.faktor == 4
    # Zusammenlegung 1:10
    v = dq.split_verdacht("s", shares("1000", a), shares("100", b), Decimal("0.02"))
    assert v.faktor == Decimal("0.1")
    # Rückkauf um 3 %: kein Split
    v = dq.split_verdacht("s", shares("1000", a), shares("970", b), Decimal("0.02"))
    assert v.faktor is None and v.ergebnis.wert == Decimal("0.97")


def test_period_lengths() -> None:
    assert dq.periode_passt(date(2024, 9, 29), date(2025, 9, 27), "FY")  # 52 Wochen
    assert dq.periode_passt(date(2023, 10, 1), date(2024, 9, 28), "FY")  # 52 Wochen
    assert not dq.periode_passt(date(2025, 1, 1), date(2025, 9, 30), "FY")  # 9 Monate
    assert dq.periode_passt(date(2025, 6, 29), date(2025, 9, 27), "Q")
    assert dq.periode_passt(None, date(2025, 9, 27), "FY")
