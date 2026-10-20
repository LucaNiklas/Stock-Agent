"""Bauschritt 4 Teil 3a: Zinsen und Damodaran-Daten (SPEC 3.6, 7.3, ADR 0006).

Testdaten in tests/fixtures/zinsen/ und tests/fixtures/damodaran/ (echte Antworten vom
19.10.2026, siehe tests/fixtures/README.md). Nur `indname.xlsx` ist nachgebaut, im Format der
echten Datei (Blatt „By industry“, gleiche Spalten).
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from stockagent import kapitalmarkt_update
from stockagent.cli import app
from stockagent.core import dcf
from stockagent.core.calc import Rechenweg
from stockagent.data import inputs, store
from stockagent.data.sources import damodaran, rates
from stockagent.data.xlsx import Mappe, excel_datum
from stockagent.paths import Paths
from tests.sec_fixtures import ROOT

FIX = ROOT / "tests" / "fixtures"
NOW = datetime(2026, 10, 19, 19, 0, tzinfo=UTC)

FIRMEN = [
    (
        "Apple Inc. (NasdaqGS:AAPL)",
        "NasdaqGS:AAPL",
        "Computers/Peripherals",
        "3663",
        "United States",
    ),
    ("SAP SE (XTRA:SAP)", "XTRA:SAP", "Software (System & Application)", "7372", "Germany"),
    ("Saputo Inc. (TSX:SAP)", "TSX:SAP", "Food Processing", "2020", "Canada"),
    ("Merck & Co. (NYSE:MRK)", "NYSE:MRK", "Drugs (Pharmaceutical)", "2834", "United States"),
    ("Pfizer Inc. (NYSE:PFE)", "NYSE:PFE", "Drugs (Pharmaceutical)", "2834", "United States"),
    (
        "Kleine Bio (NasdaqCM:KBIO)",
        "NasdaqCM:KBIO",
        "Drugs (Biotechnology)",
        "2834",
        "United States",
    ),
]


def indname_xlsx(zeilen: list[tuple[str, ...]] = FIRMEN) -> bytes:
    """Excel-Datei im Aufbau von Damodarans indname.xlsx (Inline-Text statt Shared Strings)."""
    kopf = (
        "Company Name",
        "Exchange:Ticker",
        "Industry Group",
        "Primary Sector",
        "SIC Code",
        "Country",
    )

    def zeile(nr: int, werte: tuple[str, ...]) -> str:
        zellen = "".join(
            f'<c r="{chr(65 + i)}{nr}" t="inlineStr"><is><t>{w.replace("&", "&amp;")}</t></is></c>'
            for i, w in enumerate(werte)
        )
        return f'<row r="{nr}">{zellen}</row>'

    reihen = [zeile(1, kopf)] + [
        zeile(i + 2, (f, k, b, "Sektor", s, land)) for i, (f, k, b, s, land) in enumerate(zeilen)
    ]
    blatt = f"<worksheet><sheetData>{''.join(reihen)}</sheetData></worksheet>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "xl/workbook.xml",
            '<workbook><sheets><sheet name="By industry" sheetId="1" r:id="rId1"/>'
            "</sheets></workbook>",
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
            "</Relationships>",
        )
        z.writestr("xl/worksheets/sheet1.xml", blatt)
    return buf.getvalue()


# ------------------------------------------------------------------ Quellen


def test_parse_bundesbank_and_treasury() -> None:
    eur = rates.parse_bundesbank((FIX / "zinsen" / "bundesbank_10y.csv").read_bytes())
    assert eur[0] == rates.Zins(date(2026, 9, 25), "rf_10y_EUR", Decimal("3.63"))
    assert eur[-1].datum == date(2026, 10, 19) and eur[-1].prozent == Decimal("3.49")
    assert all(z.datum.weekday() < 5 for z in eur), "Wochenenden ohne Wert fallen weg"
    usd = rates.parse_treasury((FIX / "zinsen" / "treasury_2015.csv").read_bytes())
    assert usd[-1] == rates.Zins(date(2015, 12, 31), "rf_10y_USD", Decimal("2.27"))
    with pytest.raises(rates.ZinsFormatError):
        rates.parse_treasury(b"Datum,Wert\n1,2\n")


def test_parse_damodaran_pages() -> None:
    roh = (FIX / "damodaran" / "Betas.html").read_bytes()
    betas = {b.branche: b for b in damodaran.parse_betas(roh)}
    assert damodaran.stand(roh) == "January 2026"
    assert betas["Computers/Peripherals"].beta_unverschuldet_kasse == Decimal("1.32")
    assert betas["Bank (Money Center)"].firmen == 15
    ratings = damodaran.parse_ratings((FIX / "damodaran" / "ratings.html").read_bytes())
    nicht = [r for r in ratings if r.art == "nichtfinanz"]
    assert (nicht[0].rating, nicht[-1].rating) == ("D2/D", "Aaa/AAA")
    assert nicht[-1].aufschlag_prozent == Decimal("0.40") and len(nicht) == 15
    erp = damodaran.parse_erp((FIX / "damodaran" / "ERPbymonth.xlsx").read_bytes())
    letzte = {e.monat: e for e in erp}
    assert letzte[date(2026, 10, 1)].erp == Decimal("0.036999999999999998")
    # Zeile mit Text statt Zahl („1-Sep-24“, „4.06%“) wird gelesen
    assert letzte[date(2024, 9, 1)].erp == Decimal("0.0406")


def test_xlsx_dates_and_indname() -> None:
    assert excel_datum(44834, True) == date(2026, 10, 1)  # Mac-Datei, Zählung ab 1904
    assert excel_datum(45931, False) == date(2025, 10, 1)
    firmen = damodaran.parse_indname(indname_xlsx())
    assert firmen[0].boerse_kuerzel == "NasdaqGS:AAPL" and firmen[0].sic == "3663"
    assert firmen[1].branche == "Software (System & Application)"
    assert Mappe(indname_xlsx()).blaetter == {"By industry": "xl/worksheets/sheet1.xml"}


def test_dcf_fast_and_traced_agree() -> None:
    args = (Decimal(100), Decimal("0.1"), Decimal("0.09"), Decimal("0.025"))
    schnell = dcf.barwert(*args, 10)
    r = Rechenweg("test", "1", "test", "2025")
    mit = dcf.barwert_rechenweg(r, *args, 10)
    assert abs(schnell - mit.gesamt) < Decimal("1e-20")
    # Handrechnung Jahr 1: 100 * 1,1 / 1,09 = 100,917431...
    assert next(s for s in r.schritte if s.name == "dcf_bw_1").ergebnis.startswith("100.9174311")


# ------------------------------------------------------------------ Laden


class FakeWeb:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str, agent: str, **kw: Any) -> bytes:
        self.urls.append(url)
        assert "stockagent" in agent
        if "bundesbank" in url:
            return (FIX / "zinsen" / "bundesbank_10y.csv").read_bytes()
        if "treasury" in url:
            return (FIX / "zinsen" / "treasury_2015.csv").read_bytes()
        if "bankofengland" in url:
            # Echte Antwort der Bank of England, 1. bis 19.10.2026 (Abruf 20.10.2026)
            return (FIX / "zinsen" / "boe_10y.csv").read_bytes()
        for name in ("Betas.html", "ratings.html", "wacc.html", "ERPbymonth.xlsx"):
            if url.endswith(name):
                return (FIX / "damodaran" / name).read_bytes()
        if url.endswith("indname.xlsx"):
            return indname_xlsx()
        raise AssertionError(url)


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    (tmp_path / "config").mkdir()
    for name in ("sources.yaml", "kapitalkosten.yaml"):
        (tmp_path / "config" / name).write_text(
            (ROOT / "config" / name).read_text("utf-8"), "utf-8"
        )
    return Paths(tmp_path)


def test_update_loads_everything_once(paths: Paths) -> None:
    web = FakeWeb()
    z = kapitalmarkt_update.zinsen_update(paths, fetcher=web, now=NOW)
    d = kapitalmarkt_update.damodaran_update(paths, fetcher=web, now=NOW)
    assert z.je_serie["rf_10y_EUR"][1] == date(2026, 10, 19)
    assert z.je_serie["rf_10y_GBP"][1] == date(2026, 10, 16)
    assert sum("treasury" in u for u in web.urls) == 12, "eine Datei je Jahr 2015 bis 2026"
    assert d.je_datensatz["betas_us"] == (4, "January 2026")
    assert d.je_datensatz["firms"][0] == len(FIRMEN)
    anzahl = len(web.urls)
    kapitalmarkt_update.zinsen_update(paths, fetcher=web, now=NOW)
    kapitalmarkt_update.damodaran_update(paths, fetcher=web, now=NOW)
    assert len(web.urls) == anzahl, "am selben Tag nichts neu laden"
    conn = store.connect(paths.db)
    try:
        assert store.rate_on_or_before(conn, "rf_10y_EUR", date(2026, 10, 18)).percent == Decimal(
            "3.48"
        )
        assert store.industry_beta(conn, "Computers/Peripherals").unlevered_cash == Decimal("1.32")
        assert store.industry_cost_of_debt(conn, "Computers/Peripherals") == Decimal("5.29")
        assert store.erp_on_or_before(conn, date(2026, 10, 19)).month == date(2026, 10, 1)
        assert store.rating_table(conn, "finanz")[-1].coverage_from == Decimal("3")
        # Branche: über das Kürzel, sonst häufigste Branche des SIC-Codes
        assert store.damodaran_industry_for(conn, ["NYSE:AAPL", "NasdaqGS:AAPL"]) == (
            "Computers/Peripherals",
            "NasdaqGS:AAPL",
        )
        assert store.damodaran_industry_by_sic(conn, "2834") == ("Drugs (Pharmaceutical)", 2, 3)
    finally:
        conn.close()


def test_branch_override_and_symbol_suffix(paths: Paths) -> None:
    kapitalmarkt_update.damodaran_update(paths, fetcher=FakeWeb(), now=NOW)
    conn = store.connect(paths.db)
    try:
        store.save_price_symbol(
            conn,
            store.PriceSymbol(
                "DE0007164600",
                "SAP.DE",
                "GR",
                "openfigi",
                "zugeordnet",
                "",
                "SAP",
                "EUR",
                "XETRA",
                (),
                NOW,
                NOW,
            ),
        )
        boersen = {"": ["NYSE", "NasdaqGS"], ".DE": ["XTRA", "DB"], ".TO": ["TSX"]}
        b = inputs.damodaran_branche(conn, "x", "DE0007164600", boersen, {})
        assert b is not None and b.name == "Software (System & Application)"
        assert "XTRA:SAP" in b.herkunft, "nicht Saputo in Toronto"
        fest = inputs.damodaran_branche(
            conn, "x", "DE0007164600", boersen, {"DE0007164600": "Software (Internet)"}
        )
        assert fest is not None and fest.name == "Software (Internet)"
    finally:
        conn.close()


def test_cli_markt(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    store.connect(paths.db).close()
    monkeypatch.setenv("STOCKAGENT_HOME", str(paths.root))
    web = FakeWeb()
    zinsen_echt, damodaran_echt = (
        kapitalmarkt_update.zinsen_update,
        kapitalmarkt_update.damodaran_update,
    )
    monkeypatch.setattr(
        kapitalmarkt_update,
        "zinsen_update",
        lambda p, **kw: zinsen_echt(p, fetcher=web, now=NOW, **kw),
    )
    monkeypatch.setattr(
        kapitalmarkt_update,
        "damodaran_update",
        lambda p, **kw: damodaran_echt(p, fetcher=web, now=NOW, **kw),
    )
    out = CliRunner().invoke(app, ["markt", "update"])
    assert out.exit_code == 0, out.output
    assert "rf_10y_EUR: bis 19.10.2026" in out.output
    out = CliRunner().invoke(app, ["markt", "show"])
    assert out.exit_code == 0, out.output
    assert "Damodaran betas_us: Stand January 2026" in out.output
