"""Bauschritt 1: Ablauf `universe update`, Trade-Republic-Prüfungen, Anzeige und CLI."""

from __future__ import annotations

import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from stockagent import tr_checks
from stockagent import universe as universe_mod
from stockagent.cli import app
from stockagent.data import store
from stockagent.paths import Paths
from stockagent.report import universe_view
from tests.universe_fixtures import (
    STOCKS,
    download_page,
    gleif_entities,
    gleif_zip,
    instrument_csv,
)

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def project(tmp_path: Path) -> Paths:
    (tmp_path / "config").mkdir()
    shutil.copy(ROOT / "config" / "sources.yaml", tmp_path / "config" / "sources.yaml")
    return Paths(tmp_path)


class FakeWeb:
    def __init__(
        self,
        frankfurt: list[tuple[str, str, str, str, str, str]],
        xetra: list[tuple[str, str, str, str, str, str]],
    ) -> None:
        cfg = universe_mod.load_config(Paths(ROOT))["deutsche_boerse"]
        self.pages = {
            cfg["frankfurt_page"]: download_page(cfg["frankfurt_file"]),
            cfg["xetra_page"]: download_page(cfg["xetra_file"]),
        }
        self.files = {
            cfg["frankfurt_file"]: instrument_csv(frankfurt),
            cfg["xetra_file"]: instrument_csv(xetra, market="XETR"),
        }
        self.calls: list[str] = []
        self.mapping = [("529900T8BM49AURSDO55", "DE0007164600"), (WRONG_LEI, "US0378331005")]

    def __call__(self, url: str, user_agent: str) -> bytes:
        assert "stockagent" in user_agent
        self.calls.append(url)
        if url in self.pages:
            return self.pages[url]
        if "mapping.gleif.org" in url:
            return gleif_zip(self.mapping)
        if "api.gleif.org" in url:
            return gleif_entities(ENTITIES)
        for name, content in self.files.items():
            if url.endswith(name):
                return content
        raise AssertionError(f"unerwartete URL {url}")


T0 = datetime(2026, 10, 11, 8, tzinfo=UTC)


WRONG_LEI = "5493001KJTIIGC8Y1R12"


ENTITIES = [
    ("529900T8BM49AURSDO55", "SAP SE", "DE", "DE"),
    (WRONG_LEI, "GRAND PEAK CAPITAL CORP.", "CA", "CA"),  # falsche Zuordnung wie im echten Bestand
]


def NO_SLEEP(_: float) -> None:
    pass


FRA = [s for s in STOCKS if s[1] != "DE0007164600"]


XET = [s for s in STOCKS if s[1] in ("DE0007164600", "DE0007236101")]


def _listings(paths: Paths) -> dict[str, tuple[bool, bool, str | None]]:
    conn = store.connect(paths.db)
    rows = conn.execute("SELECT isin, listed, on_xetra, lei FROM listings").fetchall()
    conn.close()
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


def test_update_first_run(project: Paths) -> None:
    res = universe_mod.update(project, fetcher=FakeWeb(FRA, XET), now=T0, sleep=NO_SLEEP)
    assert res.applied and res.stock_count == 3 and res.with_lei == 2
    assert res.lei_implausible == 1 and res.country_from_gleif == 1
    rows = _listings(project)
    assert rows["DE0007164600"] == (True, True, "529900T8BM49AURSDO55")  # nur auf Xetra
    assert rows["US0378331005"] == (True, False, WRONG_LEI)
    assert len(list(project.raw.glob("*.gz"))) == 4  # 2 Listen, Zuordnung, API


def test_update_skips_when_recent(project: Paths) -> None:
    universe_mod.update(project, fetcher=FakeWeb(FRA, XET), now=T0, sleep=NO_SLEEP)
    web = FakeWeb(FRA, XET)
    res = universe_mod.update(project, fetcher=web, now=T0 + timedelta(days=2), sleep=NO_SLEEP)
    assert not res.applied and web.calls == [] and "aktuell genug" in res.message


def test_update_blocks_large_change_without_force(project: Paths) -> None:
    universe_mod.update(project, fetcher=FakeWeb(FRA, XET), now=T0, sleep=NO_SLEEP)
    later = T0 + timedelta(days=7)
    res = universe_mod.update(project, fetcher=FakeWeb(FRA[:1], []), now=later, sleep=NO_SLEEP)
    assert not res.applied and "Nicht übernommen" in res.message
    assert all(v[0] for v in _listings(project).values())  # nichts verändert

    res = universe_mod.update(
        project, fetcher=FakeWeb(FRA[:1], []), now=later, force=True, sleep=NO_SLEEP
    )
    assert res.applied
    rows = _listings(project)
    assert rows["DE0007236101"][0] and not rows["US0378331005"][0]  # entfernt, aber erhalten
    assert rows["DE0007164600"][2] == "529900T8BM49AURSDO55"  # LEI bleibt erhalten


def test_tr_checks_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "state" / "tr_checks.yaml"
    tr_checks.record(path, "DE0007164600", True, date(2026, 10, 11))
    tr_checks.record(path, "US0378331005", False, date(2026, 10, 12))
    checks = tr_checks.load(path)
    assert checks["DE0007164600"].status is tr_checks.TrStatus.BESTAETIGT
    assert checks["US0378331005"].checked_on == date(2026, 10, 12)
    with pytest.raises(ValueError):
        tr_checks.record(path, "XX0000000000", True, date(2026, 10, 11))


def test_view_filters_and_html(project: Paths) -> None:
    universe_mod.update(project, fetcher=FakeWeb(FRA, XET), now=T0, sleep=NO_SLEEP)
    checks = {"DE0007164600": tr_checks.TrCheck(tr_checks.TrStatus.BESTAETIGT, date(2026, 10, 11))}
    conn = store.connect(project.db)
    assert [r.isin for r in universe_view.query(conn, checks, search="sap")] == ["DE0007164600"]
    assert [r.isin for r in universe_view.query(conn, checks, country="us")] == ["US0378331005"]
    assert [r.isin for r in universe_view.query(conn, checks, tr_only=True)] == ["DE0007164600"]
    rows = universe_view.query(conn, checks)
    info = universe_view.meta(conn, checks)
    conn.close()
    assert info is not None
    page = universe_view.to_html(rows, info)
    assert "3 Aktien aus den Instrumentenlisten" in page and "Stand 12.10.2026" in page
    assert "handelbar (geprüft)" in page


def test_cli_show_without_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKAGENT_HOME", str(tmp_path))
    res = CliRunner().invoke(app, ["universe", "show"])
    assert res.exit_code == 1 and "stockagent universe update" in res.stdout


def test_cli_tr_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKAGENT_HOME", str(tmp_path))
    assert CliRunner().invoke(app, ["tr-check", "de0007164600", "ja"]).exit_code == 0
    assert CliRunner().invoke(app, ["tr-check", "DE0007164600", "vielleicht"]).exit_code == 1
    assert "DE0007164600" in (tmp_path / "state" / "tr_checks.yaml").read_text()


def test_snapshot_time_is_stored_as_utc(project: Paths) -> None:
    """DuckDB würde Zeiten mit Zeitzone in Ortszeit umrechnen."""
    universe_mod.update(project, fetcher=FakeWeb(FRA, XET), now=T0, sleep=NO_SLEEP)
    conn = store.connect(project.db)
    raw = conn.execute("SELECT retrieved_at FROM universe_snapshots").fetchone()
    assert raw is not None and raw[0] == T0.replace(tzinfo=None)
    assert store.last_retrieved_at(conn) == T0
    conn.close()


def test_paths_find_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STOCKAGENT_HOME", raising=False)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "sources.yaml").write_text("x: 1")
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    assert Paths.default().root == tmp_path.resolve()


def test_cli_update_outside_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STOCKAGENT_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    res = CliRunner().invoke(app, ["universe", "update"])
    assert res.exit_code == 1 and "Projektordner nicht gefunden" in res.stdout
    assert not (tmp_path / "data").exists()


def test_update_sets_countries(project: Paths) -> None:
    universe_mod.update(project, fetcher=FakeWeb(FRA, XET), now=T0, sleep=NO_SLEEP)
    conn = store.connect(project.db)
    rows = dict(
        (r[0], r[1:])
        for r in conn.execute(
            "SELECT isin, country, country_source, lei_plausible, hq_country FROM listings"
        ).fetchall()
    )
    conn.close()
    assert rows["DE0007164600"] == ("DE", "gleif", True, "DE")  # SAP
    assert rows["US0378331005"] == ("US", "isin", False, "CA")  # falsche LEI nicht übernommen
    assert rows["DE0007236101"] == ("DE", "isin", None, None)  # ohne LEI


def test_update_prunes_old_gleif_raw(project: Paths) -> None:
    for week in range(4):
        web = FakeWeb(FRA, XET)
        web.mapping = [*web.mapping, (f"LEI_WEEK_{week:011d}", f"XX000000000{week}")]
        res = universe_mod.update(
            project, fetcher=web, now=T0 + timedelta(days=7 * week), sleep=NO_SLEEP
        )
        assert res.applied
    conn = store.connect(project.db)
    keep = store.raw_in_recent_snapshots(conn, ("gleif_mapping", "gleif_entities"), 2)
    conn.close()
    gleif_files = set()
    for meta in project.raw.glob("*.json"):
        if "gleif" in meta.read_text():
            gleif_files.add(meta.stem)
    assert gleif_files == keep and len(keep) == 3  # zwei Zuordnungsdateien, eine API-Antwort
    assert res.pruned_raw == 1
    boerse = [m for m in project.raw.glob("*.json") if "deutsche-boerse" in m.read_text()]
    assert len(boerse) == 2  # Börsenlisten werden nie gelöscht (gleicher Inhalt, je einmal)


def test_outdated_schema_is_reported(tmp_path: Path) -> None:
    import duckdb

    db = tmp_path / "alt.duckdb"
    conn = duckdb.connect(str(db))
    conn.execute("CREATE TABLE listings (isin VARCHAR)")
    conn.close()
    with pytest.raises(store.SchemaOutdated, match="neu aufbauen"):
        store.connect(db)
