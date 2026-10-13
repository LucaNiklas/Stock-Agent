"""Bauschritt 2: Ablauf Zuordnung, Stammdaten, Werte und Prüfungen mit echten Testdaten."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from stockagent import sec_update
from stockagent.cli import app
from stockagent.data import store
from stockagent.data.http import FetchError
from stockagent.data.sources import openfigi, sec
from stockagent.paths import Paths
from tests.sec_fixtures import AGENT, APPLE, JPM, NOW, PAGERDUTY, FakeWeb, no_sleep, project, read


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Paths:
    monkeypatch.setenv("SEC_USER_AGENT", AGENT)
    return project(tmp_path)


TICKERS = {
    "AAPL": sec.TickerEntry(APPLE, "Apple Inc.", "AAPL", "Nasdaq"),
    "JPM": sec.TickerEntry(JPM, "JPMORGAN CHASE & CO", "JPM", "NYSE"),
}


def listing(name: str = "APPLE INC.", lei_name: str | None = None) -> sec_update.Listing:
    return sec_update.Listing("US0378331005", name, lei_name)


def figi(ticker: str | None, note: str = "") -> openfigi.FigiResult:
    return openfigi.FigiResult("US0378331005", ticker, "APPLE INC", note)


def test_decide_ticker_with_plausible_name() -> None:
    r = sec_update.decide(listing(), figi("AAPL"), TICKERS, {}, (False, None))
    assert (r.cik, r.status, r.method) == (APPLE, "zugeordnet", "openfigi")


def test_decide_ticker_with_wrong_name_stays_empty() -> None:
    r = sec_update.decide(
        sec_update.Listing("X", "GRAND PEAK CAPITAL", None),
        openfigi.FigiResult("X", "AAPL", "GRAND PEAK CAPITAL", ""),
        TICKERS,
        {},
        (False, None),
    )
    assert r.cik is None and r.status == "unsicher"


def test_decide_ticker_not_at_sec() -> None:
    r = sec_update.decide(listing(), figi("XYZ"), TICKERS, {}, (False, None))
    assert r.cik is None and r.status == "keine" and "nicht in der Tickerliste" in r.detail


def test_decide_name_fallback_only_with_unique_lei_name() -> None:
    by_name = {("APPLE",): [TICKERS["AAPL"]]}
    r = sec_update.decide(
        listing(lei_name="Apple Inc."), figi(None), TICKERS, by_name, (False, None)
    )
    assert (r.cik, r.method) == (APPLE, "name")
    # ohne LEI-Namen kein Namensabgleich mit dem abgekürzten Börsennamen
    r = sec_update.decide(listing(), figi(None, "kein Ticker"), TICKERS, by_name, (False, None))
    assert r.cik is None and r.status == "keine"


def test_decide_override_wins() -> None:
    r = sec_update.decide(listing(), figi("AAPL"), TICKERS, {}, (True, None))
    assert (r.cik, r.status, r.method) == (None, "keine", "manuell")
    r = sec_update.decide(listing(), None, TICKERS, {}, (True, JPM))
    assert (r.cik, r.method) == (JPM, "manuell")


def test_overrides_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "state" / "cik_overrides.yaml"
    sec_update.record_override(path, "US0378331005", "320193", date(2026, 10, 13))
    sec_update.record_override(path, "US0000000000", None, date(2026, 10, 13))
    assert sec_update.load_overrides(path) == {"US0378331005": APPLE, "US0000000000": None}
    assert path.read_text().startswith("# Lucas Zuordnungen")


def test_update_full_run_for_apple(paths: Paths) -> None:
    web = FakeWeb()
    res = sec_update.update(paths, isins=["US0378331005"], fetcher=web, sleep=no_sleep, now=NOW)
    assert res.mapping.status["zugeordnet"] == 1
    (loaded,) = res.loaded
    assert loaded.error is None and loaded.name == "Apple Inc." and loaded.facts > 1000
    assert loaded.flags["stopp"] == 0 and loaded.flags["warnung"] == 0
    conn = store.connect(paths.db)
    issuer = store.load_issuer(conn, "sec:0000320193")
    assert issuer is not None
    assert (issuer.sector_sic, issuer.country, issuer.lei) == ("3571", "US", "HWUPKR0MPOU8FGXBT394")
    checks = {f.check_id for f in store.load_dq_flags(conn, "sec:0000320193")}
    assert checks == {f"DQ-0{i}" for i in range(1, 9)}  # alle acht Prüfungen aus SPEC 3.2
    conn.close()
    # Rohdaten liegen unverändert in data/raw/
    assert any("companyfacts" in p.read_text() for p in paths.raw.glob("*.json"))


def test_second_run_needs_no_new_mapping(paths: Paths) -> None:
    sec_update.update(paths, isins=["US0378331005"], fetcher=FakeWeb(), sleep=no_sleep, now=NOW)
    web = FakeWeb()
    res = sec_update.update(paths, isins=["US0378331005"], fetcher=web, sleep=no_sleep, now=NOW)
    assert res.mapping.abgefragt == 0 and web.posts == []
    assert res.loaded[0].error is None


def test_master_data_for_all_but_values_only_for_selection(paths: Paths) -> None:
    web = FakeWeb()
    res = sec_update.update(paths, fetcher=web, sleep=no_sleep, now=NOW)
    assert res.mapping.status["zugeordnet"] == 3 and res.mapping.status["keine"] == 1
    assert res.master_loaded == 3 and res.loaded == []
    assert not any("companyfacts" in u for u in web.calls)
    conn = store.connect(paths.db)
    assert store.load_issuer(conn, f"sec:{PAGERDUTY}") is not None
    conn.close()
    # Innerhalb von master_refresh_days nicht erneut
    res = sec_update.update(paths, fetcher=FakeWeb(), sleep=no_sleep, now=NOW)
    assert res.master_loaded == 0 and res.master_skipped == 3


def test_unknown_isin_is_reported(paths: Paths) -> None:
    res = sec_update.update(
        paths, isins=["US0000000000"], fetcher=FakeWeb(), sleep=no_sleep, now=NOW
    )
    assert res.loaded[0].error is not None and "keine CIK" in res.loaded[0].error


def test_cli_sec_show_and_map(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    sec_update.update(paths, isins=["US0378331005"], fetcher=FakeWeb(), sleep=no_sleep, now=NOW)
    monkeypatch.setenv("STOCKAGENT_HOME", str(paths.root))
    out = CliRunner().invoke(app, ["sec", "show", "US0378331005"])
    assert out.exit_code == 0, out.output
    assert "Electronic Computers" in out.output and "416.161.000.000" in out.output
    assert "DQ-05 ok" in out.output
    out = CliRunner().invoke(app, ["sec", "map", "US0000000000", "keine"])
    assert out.exit_code == 0 and "kein SEC-Melder" in out.output


def test_cli_sec_update_without_agent(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEC_USER_AGENT")
    monkeypatch.setenv("STOCKAGENT_HOME", str(paths.root))
    out = CliRunner().invoke(app, ["sec", "update", "--isin", "US0378331005"])
    assert out.exit_code == 1 and "SEC_USER_AGENT" in out.output


def test_override_for_foreign_isin(paths: Paths) -> None:
    conn = store.connect(paths.db)
    conn.execute("UPDATE listings SET isin_country = 'DE' WHERE isin = 'US0000000000'")
    conn.close()
    sec_update.record_override(
        sec_update.overrides_path(paths), "US0000000000", PAGERDUTY, date(2026, 10, 13)
    )
    res = sec_update.update(paths, fetcher=FakeWeb(), sleep=no_sleep, now=NOW)
    conn = store.connect(paths.db)
    row = store.load_isin_cik(conn)["US0000000000"]
    conn.close()
    assert (row.cik, row.method) == (PAGERDUTY, "manuell") and res.mapping.geprueft == 4


def test_mapping_blocks_survive_abort(paths: Paths) -> None:
    web = FakeWeb()

    def fails_on_second_post(url: str, agent: str, **kw: object) -> bytes:
        if "openfigi" in url and web.posts:
            raise FetchError("Verbindung abgebrochen")
        return web(url, agent, **kw)

    figi = openfigi.OpenFigiClient(
        {
            "mapping_url": "https://api.openfigi.com/v3/mapping",
            "jobs_per_request": 10,
            "requests_per_minute": 25,
        },
        "ua",
        paths.raw,
        fetcher=fails_on_second_post,
        sleep=no_sleep,
    )
    tickers = sec.parse_tickers(read("company_tickers_exchange.json"))
    conn = store.connect(paths.db)
    with pytest.raises(FetchError):
        sec_update.map_isins(conn, figi, tickers, {}, NOW, 90, block=2)
    assert len(store.load_isin_cik(conn)) == 2  # erster Block ist gespeichert
    conn.close()


def test_openfigi_pause_also_between_calls(tmp_path: Path) -> None:
    waits: list[float] = []

    def fetcher(url: str, agent: str, **kw: object) -> bytes:
        return b'[{"warning": "No identifier found."}]'

    cfg = {"mapping_url": "u", "jobs_per_request": 10, "requests_per_minute": 25}
    client = openfigi.OpenFigiClient(cfg, "ua", tmp_path, fetcher=fetcher, sleep=waits.append)
    client.map(["A"])
    client.map(["B"])
    assert waits == [2.4]
