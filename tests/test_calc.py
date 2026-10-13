"""HR-19: Rechenweg mit Prüfpunkten (SPEC 12.7)."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest

from stockagent.core.calc import (
    KATALOG,
    Eingabe,
    PruefpunktVerletzt,
    RechenFehler,
    Rechenweg,
    Stufe,
    berechne,
    rechne,
)


def ein(wert: str, waehrung: str | None = "USD", ende: date = date(2025, 9, 27)) -> Eingabe:
    return Eingabe(Decimal(wert), "test", "monetary", ende, waehrung)


def test_catalog_has_cp01_to_cp08() -> None:
    assert sorted(KATALOG) == [f"CP-0{i}" for i in range(1, 9)]
    assert KATALOG["CP-05"].stufe is Stufe.WARNUNG


def test_formula_text_is_the_calculation() -> None:
    assert berechne("ebit / umsatz", ebit=Decimal(30), umsatz=Decimal(120)) == Decimal("0.25")
    assert berechne("abs(a - b) / max(a, b)", a=3, b=5) == Decimal("0.4")
    assert berechne("runde(x)", x=Decimal("3.98")) == Decimal(4)
    assert berechne("0.005 * x", x=200) == Decimal("1.000")


@pytest.mark.parametrize("formel", ["a ** 2", "__import__('os')", "a if a else b", "a.real", "x"])
def test_formula_rejects_everything_else(formel: str) -> None:
    with pytest.raises(RechenFehler):
        berechne(formel, a=1, b=2)


def test_steps_are_recorded_with_inputs_and_provenance() -> None:
    r = Rechenweg("marge", "1.0", "sec:0000320193", "FY2025", pflicht=("CP-01", "CP-02"))

    def rechnung(r: Rechenweg) -> Decimal:
        ebit, umsatz = ein("30"), ein("120")
        r.pruefe_eingaben(ebit, umsatz)
        m = r.schritt("marge", "ebit / umsatz", ebit=ebit, umsatz=umsatz)
        r.pruefe("CP-02", "Marge zwischen -1 und 1", -1 <= m <= 1)
        return m

    erg = rechne(r, rechnung)
    assert erg.wert == Decimal("0.25")
    trace = json.loads(erg.rechenweg_json())
    assert trace["schritte"][0]["formel"] == "ebit / umsatz"
    assert trace["schritte"][0]["eingaben"]["ebit"]["quelle"] == "test"
    assert all(p["bestanden"] for p in trace["pruefungen"])


def test_failed_checkpoint_stops_calculation() -> None:
    weiter = []

    def rechnung(r: Rechenweg) -> Decimal:
        x = r.schritt("x", "a - b", a=1, b=5)
        r.pruefe("CP-02", "x positiv", x > 0)
        weiter.append(True)  # darf nie erreicht werden
        return x

    erg = rechne(Rechenweg("t", "1.0", "s", "p"), rechnung)
    assert erg.unknown
    assert erg.ungereimtheit == "INC-15"
    assert erg.grund == "CP-02: x positiv"
    assert weiter == []


def test_warning_does_not_stop() -> None:
    def rechnung(r: Rechenweg) -> Decimal:
        r.pruefe("CP-05", "kein Ausreißer", False)
        return Decimal(1)

    erg = rechne(Rechenweg("t", "1.0", "s", "p"), rechnung)
    assert erg.wert == 1
    assert erg.warnungen == ("CP-05: kein Ausreißer",)


def test_division_by_zero_is_cp02_stop() -> None:
    erg = rechne(Rechenweg("t", "1.0", "s", "p"), lambda r: r.schritt("q", "a / b", a=1, b=0))
    assert erg.unknown
    assert erg.grund is not None and erg.grund.startswith("CP-02")


def test_missing_mandatory_checkpoint_is_programming_error() -> None:
    r = Rechenweg("t", "1.0", "s", "p", pflicht=("CP-03",))
    with pytest.raises(RuntimeError, match="CP-03"):
        rechne(r, lambda r: Decimal(1))


def test_cp01_detects_mixed_currency_and_period() -> None:
    r = Rechenweg("t", "1.0", "s", "p")
    with pytest.raises(PruefpunktVerletzt, match="CP-01"):
        r.pruefe_eingaben(ein("1"), ein("1", waehrung="EUR"))
    r = Rechenweg("t", "1.0", "s", "p")
    with pytest.raises(PruefpunktVerletzt, match="CP-01"):
        r.pruefe_eingaben(ein("1"), ein("1", ende=date(2024, 9, 28)))


def test_trace_is_stored_and_repeatable() -> None:
    """CP-08: zweimal gerechnet ergibt bitgleich denselben Rechenweg."""

    def rechnung(r: Rechenweg) -> Decimal:
        m = r.median("median", [ein("3"), ein("1"), ein("2")])
        return r.schritt("doppelt", "2 * m", m=m)

    a = rechne(Rechenweg("t", "1.0", "s", "p"), rechnung)
    b = rechne(Rechenweg("t", "1.0", "s", "p"), rechnung)
    assert a.wert == Decimal(4)
    assert a.rechenweg_json() == b.rechenweg_json()
