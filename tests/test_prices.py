"""Bauschritt 4: Kurse von Yahoo (ADR 0005).

Testdaten in tests/fixtures/yahoo/: echte Antworten von Yahoo und OpenFIGI vom 14.10.2026,
gekürzt auf die letzten 5 Handelstage (Quelle in `_quelle` jeder Datei). Nur
`chart_falscher_name.json` ist nachgebaut, um eine falsche Zuordnung zu prüfen.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from stockagent import prices_update
from stockagent.cli import app
from stockagent.core.anzeige import formatiere
from stockagent.data import store
from stockagent.data.http import NotFound
from stockagent.data.sources import yahoo
from stockagent.data.sources.openfigi import Listing
from stockagent.paths import Paths
from tests.sec_fixtures import ROOT, _listing

FIX = ROOT / "tests" / "fixtures" / "yahoo"
CFG = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text("utf-8"))["yahoo"]
# Nach Handelsschluss in Frankfurt und London am 14.10.2026 (15:30 UTC)
NOW = datetime(2026, 10, 14, 18, 0, tzinfo=UTC)
SAP, BT = "DE0007164600", "GB0030913577"


def roh(name: str) -> bytes:
    return (FIX / name).read_bytes()


# ------------------------------------------------------------------ Symbole


def test_symbol_rules() -> None:
    e = CFG["endungen"]
    assert yahoo.symbol(Listing("GR", "SAP", None, None), e) == "SAP.DE"
    assert yahoo.symbol(Listing("US", "BRK/B", None, None), e) == "BRK-B"
    assert yahoo.symbol(Listing("LN", "BT/A", None, None), e) == "BT-A.L"
    assert yahoo.symbol(Listing("LN", "RR/", None, None), e) == "RR.L"
    assert yahoo.symbol(Listing("HK", "700", None, None), e) == "0700.HK"
    assert yahoo.symbol(Listing("JP", "7203", None, None), e) == "7203.T"
    assert yahoo.symbol(Listing("XX", "ABC", None, None), e) is None


def test_candidates_prefer_home_market() -> None:
    notierungen = [
        Listing("GF", "SAP", None, None),
        Listing("US", "SAPGF", None, None),
        Listing("GR", "SAP", None, None),
        Listing("XX", "SAP", None, None),
    ]
    assert yahoo.kandidaten(notierungen, "DE", CFG) == [
        ("GR", "SAP.DE"),
        ("US", "SAPGF"),
        ("GF", "SAP.F"),
    ]
    # Land ohne eigene Börse in der Liste: USA, dann Xetra, dann Frankfurt
    assert yahoo.kandidaten(notierungen, "KY", CFG)[0] == ("US", "SAPGF")


# ------------------------------------------------------------------ Antwort lesen


def test_parse_real_chart() -> None:
    c = yahoo.parse_chart(roh("chart_sap_de.json"))
    assert (c.symbol, c.waehrung, c.art, c.name) == ("SAP.DE", "EUR", "EQUITY", "SAP SE")
    assert [k.datum.isoformat() for k in c.kurse][:2] == ["2026-10-08", "2026-10-09"]
    # Wert wie geliefert, Gleitkomma-Rauschen von Yahoo eingeschlossen
    assert c.kurse[-1].schluss == Decimal("197.4199981689453") and c.kurse[-1].volumen == 887238
    assert [(e.datum, e.wert) for e in c.ereignisse] == [
        (date(2025, 5, 14), Decimal("2.35")),
        (date(2026, 5, 6), Decimal("2.5")),
    ]
    # Reguläres Handelsende am 14.10.2026 in Frankfurt: 17:30 Ortszeit
    assert c.handelsende == datetime(2026, 10, 14, 15, 30, tzinfo=UTC)


def test_split_as_numerator_and_denominator() -> None:
    c = yahoo.parse_chart(roh("chart_aapl.json"))
    (split,) = [e for e in c.ereignisse if e.art == "split"]
    assert (split.datum, split.zaehler, split.nenner) == (date(2020, 8, 31), 4, 1)


def test_pence_stay_as_delivered() -> None:
    c = yahoo.parse_chart(roh("chart_bt_a_l.json"))
    assert c.waehrung == "GBp" and c.kurse[-1].schluss == Decimal("197.75")


def test_unknown_symbol_and_broken_answer() -> None:
    with pytest.raises(yahoo.YahooError, match="delisted"):
        yahoo.parse_chart(roh("chart_unbekannt.json"))
    with pytest.raises(yahoo.YahooFormatError):
        yahoo.parse_chart(b"<html>Bitte bestaetigen</html>")


def test_display_rounds_float_noise() -> None:
    assert formatiere(Decimal("345.79998779296875"), "kurs", 4, "USD") == "345,80 USD"
    assert formatiere(Decimal("3011.0"), "kurs", 4, "JPY") == "3.011,00 JPY"
    assert formatiere(Decimal("0.01234567"), "kurs", 4) == "0,0123"


# ------------------------------------------------------------------ Ablauf


class FakeWeb:
    """OpenFIGI und Yahoo aus den Testdaten. Unbekannte Symbole: 404 wie bei Yahoo."""

    def __init__(self, charts: dict[str, str]) -> None:
        self.charts = charts
        self.calls: list[str] = []
        self.figi = json.loads(roh("openfigi_listings.json"))["antworten"]

    def __call__(self, url: str, agent: str, **kw: Any) -> bytes:
        self.calls.append(url)
        assert "stockagent" in agent, "eigener User-Agent, kein Browser"
        if "openfigi" in url:
            isins = [j["idValue"] for j in json.loads(kw["data"])]
            antworten = [self.figi.get(i, [{"warning": "No identifier found."}])[0] for i in isins]
            return json.dumps(antworten).encode()
        sym = url.split("/chart/")[1].split("?")[0]
        if sym not in self.charts:
            raise NotFound(f"{url}: nicht gefunden (404)")
        return roh(self.charts[sym])


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "sources.yaml").write_text(
        (ROOT / "config" / "sources.yaml").read_text("utf-8"), "utf-8"
    )
    p = Paths(tmp_path)
    conn = store.connect(p.db)
    rows = [
        _listing(SAP, "SAP SE O.N.", None, None),
        _listing(BT, "BT GROUP PLC      LS 0.05", None, None),
    ]
    rows = [
        r.__class__(**{**r.__dict__, "country": c}) for r, c in zip(rows, ["DE", "GB"], strict=True)
    ]
    store.apply_snapshot(
        conn, rows, retrieved_at=NOW, source_as_of=date(2026, 10, 9), raw=[], forced=False
    )
    conn.close()
    return p


def lauf(paths: Paths, web: FakeWeb, isins: list[str], **kw: Any) -> Any:
    return prices_update.update(
        paths, isins, fetcher=web, sleep=lambda _: None, now=kw.pop("now", NOW), **kw
    )


def test_first_load_maps_symbol_and_stores_prices(paths: Paths) -> None:
    web = FakeWeb({"SAP.DE": "chart_sap_de.json"})
    (r,) = lauf(paths, web, [SAP])
    assert r.fehler is None and r.symbol == "SAP.DE" and r.kurse_neu == 5
    assert r.letzter.schluss == Decimal("197.4199981689453") and r.waehrung == "EUR"
    assert "range=10y" in web.calls[-1]
    conn = store.connect(paths.db)
    sym = store.load_price_symbol(conn, SAP)
    kurse = store.load_prices(conn, SAP)
    ereignisse = store.load_price_events(conn, SAP)
    conn.close()
    assert sym is not None and sym.status == "zugeordnet" and sym.exch_code == "GR"
    assert kurse[-1].date == date(2026, 10, 14) and kurse[0].source == "yahoo"
    assert [e.kind for e in ereignisse] == ["dividende", "dividende"]
    assert any("finance.yahoo.com" in p.read_text() for p in paths.raw.glob("*.json"))


def test_running_day_is_not_stored(paths: Paths) -> None:
    """Vor 17:30 in Frankfurt ist der Kurs vom 14.10. ein laufender Kurs, kein Schlusskurs."""
    web = FakeWeb({"SAP.DE": "chart_sap_de.json"})
    (r,) = lauf(paths, web, [SAP], now=datetime(2026, 10, 14, 12, 0, tzinfo=UTC))
    assert r.kurse_neu == 4 and r.letzter.datum == date(2026, 10, 13)
    assert r.laufend is not None and r.laufend.datum == date(2026, 10, 14)
    conn = store.connect(paths.db)
    assert store.load_prices(conn, SAP)[-1].date == date(2026, 10, 13)
    conn.close()


def test_same_day_is_skipped_and_later_fetches_only_recent(paths: Paths) -> None:
    web = FakeWeb({"SAP.DE": "chart_sap_de.json"})
    lauf(paths, web, [SAP])
    anzahl = len(web.calls)
    (r,) = lauf(paths, web, [SAP])
    assert r.uebersprungen and len(web.calls) == anzahl
    (r,) = lauf(paths, web, [SAP], now=datetime(2026, 10, 16, 20, 0, tzinfo=UTC))
    assert not r.uebersprungen and "range=3mo" in web.calls[-1]
    assert not any("openfigi" in u for u in web.calls[anzahl:])


def test_wrong_name_is_not_accepted(paths: Paths) -> None:
    web = FakeWeb({"SAP.DE": "chart_falscher_name.json", "SAPGF": "chart_falscher_name.json"})
    (r,) = lauf(paths, web, [SAP])
    assert r.symbol is None and r.status == "unsicher"
    assert "Name passt nicht" in str(r.fehler) and "SAP.F: Yahoo kennt SAP.F nicht" in str(r.fehler)


def test_falls_back_to_next_listing(paths: Paths) -> None:
    web = FakeWeb({"SAP.F": "chart_sap_de.json"})  # SAP.DE und SAPGF unbekannt (404)
    (r,) = lauf(paths, web, [SAP])
    assert r.symbol == "SAP.F"


def test_pence_and_stale_price_warning(paths: Paths) -> None:
    web = FakeWeb({"BT-A.L": "chart_bt_a_l.json"})
    (r,) = lauf(paths, web, [BT], now=datetime(2026, 11, 30, 20, 0, tzinfo=UTC))
    assert r.symbol == "BT-A.L" and r.waehrung == "GBp"
    assert any("Handel ausgesetzt" in w for w in r.warnungen)


def test_override_and_cli(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKAGENT_HOME", str(paths.root))
    out = CliRunner().invoke(app, ["prices", "map", SAP, "keine"])
    assert out.exit_code == 0, out.output
    (r,) = lauf(paths, FakeWeb({}), [SAP])
    assert r.symbol is None and "Lucas Vorgabe" in str(r.fehler)
    CliRunner().invoke(app, ["prices", "map", SAP, "sap.de"])
    lauf(paths, FakeWeb({"SAP.DE": "chart_sap_de.json"}), [SAP])
    out = CliRunner().invoke(app, ["prices", "show", SAP])
    assert out.exit_code == 0, out.output
    assert "SAP.DE" in out.output and "197,42 EUR" in out.output and "Dividenden: 2" in out.output


def test_disabled_source(paths: Paths) -> None:
    cfg = paths.config / "sources.yaml"
    cfg.write_text(cfg.read_text("utf-8").replace("  enabled: true", "  enabled: false"), "utf-8")
    (r,) = lauf(paths, FakeWeb({}), [SAP])
    assert r.fehler == "Kursquelle Yahoo ist ausgeschaltet"
