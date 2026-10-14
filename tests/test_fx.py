"""Bauschritt 4: Wechselkurse der EZB und Umrechnung im Rechenweg (SPEC 5.2).

`tests/fixtures/ecb/exr_2026-10-14.csv` ist eine echte Antwort der EZB vom 14.10.2026
(Rohdatei 1ae898e7267ba042..., 29 Währungen, ein Tag). Die Kurse vom 26.09.2025 in den
Rechnungen unten stammen aus dem Erstabruf (Rohdatei bf36874ae996eefe...): USD 1,1672 und
GBP 0,874 je EUR.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from stockagent import fx_update
from stockagent.core import fx
from stockagent.core.calc import Eingabe, PruefpunktVerletzt, Rechenweg
from stockagent.data import store
from stockagent.data.sources.fx import EcbFormatError, parse_csv
from stockagent.paths import Paths
from tests.sec_fixtures import ROOT

FIX = ROOT / "tests" / "fixtures" / "ecb" / "exr_2026-10-14.csv"
TAG = date(2025, 9, 26)
UNTER = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR"}


def _kurs(w: str, wert: str) -> Eingabe:
    return Eingabe(Decimal(wert), f"EZB-Referenzkurs {w} je EUR {TAG}", "fx", TAG)


USD, GBP = _kurs("USD", "1.1672"), _kurs("GBP", "0.874")


def _rw() -> Rechenweg:
    return Rechenweg("test", "1", "test", TAG.isoformat())


def _preis(wert: str, waehrung: str) -> Eingabe:
    return Eingabe(Decimal(wert), "Testkurs", "per_share", TAG, waehrung)


# ------------------------------------------------------------------ EZB-Antwort


def test_parse_real_ecb_answer() -> None:
    kurse = {k.waehrung: k for k in parse_csv(FIX.read_bytes())}
    assert len(kurse) == 29
    assert kurse["USD"].je_eur == Decimal("1.1195") and kurse["USD"].datum == date(2026, 10, 14)
    assert kurse["GBP"].je_eur == Decimal("0.84385") and kurse["JPY"].je_eur == Decimal("177.39")


def test_parse_rejects_other_columns() -> None:
    with pytest.raises(EcbFormatError):
        parse_csv(b"A,B\n1,2\n")


# ------------------------------------------------------------------ Umrechnung


def test_pence_to_dollar_over_euro() -> None:
    """25.000 GBp / 100 = 250 GBP; 250 / 0,874 * 1,1672 = 333,8673 USD."""
    r = _rw()
    erg = fx.umrechnen(
        r, "kurs_usd", _preis("25000", "GBp"), "USD", {"GBP": GBP, "USD": USD}, UNTER
    )
    assert erg.waehrung == "USD" and "GBp -> USD" in erg.quelle
    assert erg.wert.quantize(Decimal("0.0001")) == Decimal("333.8673")
    (s,) = r.schritte
    assert s.eingaben["teiler"] == "100" and "GBP" in s.eingaben and "USD" in s.eingaben


def test_pence_to_pound_needs_no_rate() -> None:
    erg = fx.umrechnen(_rw(), "kurs_gbp", _preis("25000", "GBp"), "GBP", {}, UNTER)
    assert erg.wert == Decimal(250) and erg.waehrung == "GBP"


def test_dollar_to_euro() -> None:
    """255,46 USD / 1,1672 = 218,8657 EUR."""
    erg = fx.umrechnen(_rw(), "kurs_eur", _preis("255.46", "USD"), "EUR", {"USD": USD}, UNTER)
    assert erg.wert.quantize(Decimal("0.0001")) == Decimal("218.8657")


def test_missing_rate_stops() -> None:
    with pytest.raises(PruefpunktVerletzt) as exc:
        fx.umrechnen(_rw(), "kurs", _preis("10", "JPY"), "USD", {"USD": USD}, UNTER)
    assert exc.value.cp_id == "CP-01"


# ------------------------------------------------------------------ Laden


class FakeEcb:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str, agent: str, **kw: Any) -> bytes:
        self.urls.append(url)
        assert "stockagent" in agent
        return FIX.read_bytes()


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "sources.yaml").write_text(
        (ROOT / "config" / "sources.yaml").read_text("utf-8"), "utf-8"
    )
    return Paths(tmp_path)


def test_update_loads_once_a_day_and_continues(paths: Paths) -> None:
    web = FakeEcb()
    jetzt = datetime(2026, 10, 14, 18, 0, tzinfo=UTC)
    r = fx_update.update(paths, fetcher=web, now=jetzt)
    assert r.neu == 29 and r.bis == date(2026, 10, 14)
    assert "startPeriod=2015-01-01" in web.urls[0] and "detail=dataonly" in web.urls[0]
    assert fx_update.update(paths, fetcher=web, now=jetzt).uebersprungen
    fx_update.update(paths, fetcher=web, now=datetime(2026, 10, 20, 18, 0, tzinfo=UTC))
    assert "startPeriod=2026-10-14" in web.urls[-1]
    fx_update.update(paths, fetcher=web, now=jetzt, refresh=True)
    assert "startPeriod=2015-01-01" in web.urls[-1]
    conn = store.connect(paths.db)
    # Wochenende: der Kurs vom letzten Kurstag davor gilt
    k = store.fx_on_or_before(conn, "USD", date(2026, 10, 18))
    zahl = conn.execute("SELECT count(*) FROM fx_rates").fetchone()
    conn.close()
    assert k is not None and k.per_eur == Decimal("1.1195") and k.date == date(2026, 10, 14)
    assert zahl == (29,), "Wiederholte Abrufe ersetzen, statt doppelt zu speichern"
