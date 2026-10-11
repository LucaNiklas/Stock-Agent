"""Bauschritt 1: Universum aus Deutscher Börse, LEI aus GLEIF, Prüfungen und Anzeige."""

from __future__ import annotations

import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from stockagent import tr_checks
from stockagent import universe as universe_mod
from stockagent.cli import app
from stockagent.core.identifiers import change_exceeds, isin_is_valid
from stockagent.data import rawstore, store
from stockagent.data.sources import deutsche_boerse, gleif
from stockagent.data.sources.deutsche_boerse import SourceFormatError
from stockagent.paths import Paths
from stockagent.report import universe_view
from tests.universe_fixtures import STOCKS, download_page, gleif_zip, instrument_csv

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- ISIN


@pytest.mark.parametrize(
    "isin",
    [
        "US0378331005",
        "DE0007164600",
        "DE0008404005",
        "GB0002875804",
        "KYG9830T1067",
        "DE000ENER6Y0",
    ],
)
def test_isin_valid(isin: str) -> None:
    assert isin_is_valid(isin)


@pytest.mark.parametrize(
    "isin",
    ["US0378331006", "DE0007164601", "us0378331005", "US037833100", "XX00000000001", ""],
)
def test_isin_invalid(isin: str) -> None:
    assert not isin_is_valid(isin)


@pytest.mark.parametrize(
    ("prev", "cur", "exceeds"),
    [
        (1000, 1050, False),
        (1000, 1051, True),
        (1000, 949, True),
        (1000, 950, False),
        (0, 10, False),
    ],
)
def test_change_exceeds(prev: int, cur: int, exceeds: bool) -> None:
    assert change_exceeds(prev, cur, 5) is exceeds


# ---------------------------------------------------------------- Deutsche Börse


def test_parse_keeps_only_stocks_and_trims_wkn() -> None:
    f = deutsche_boerse.parse(instrument_csv(STOCKS))
    assert f.market == "XFRA" and f.as_of == date(2026, 10, 12)
    assert [i.isin for i in f.instruments] == ["DE0007236101", "US0378331005", "DE0007164600"]
    assert f.instruments[0].wkn == "723610"
    assert f.instruments[1].isin_country == "US"


def test_parse_rejects_missing_column() -> None:
    raw = instrument_csv(STOCKS).replace(b"Primary Market MIC Code", b"Primary MIC")
    with pytest.raises(SourceFormatError, match="Spalten fehlen"):
        deutsche_boerse.parse(raw)


def test_parse_rejects_broken_row() -> None:
    raw = instrument_csv(STOCKS) + b"Active;Active;KAPUTT\n"
    with pytest.raises(SourceFormatError, match="Spalten"):
        deutsche_boerse.parse(raw)


def test_parse_rejects_unknown_layout() -> None:
    with pytest.raises(SourceFormatError):
        deutsche_boerse.parse(b"ISIN;Name\nDE0007164600;SAP\n")


def test_find_file_url() -> None:
    page = download_page("t7-xfra-BF-allTradableInstruments.csv").decode()
    url = deutsche_boerse.find_file_url(
        page, "t7-xfra-BF-allTradableInstruments.csv", "https://example.org/cash-en/page"
    )
    assert (
        url == "https://example.org/resource/blob/2/def/data/t7-xfra-BF-allTradableInstruments.csv"
    )


def test_find_file_url_missing() -> None:
    with pytest.raises(SourceFormatError, match="0 Links"):
        deutsche_boerse.find_file_url("<html></html>", "x.csv", "https://example.org/")


# ---------------------------------------------------------------- GLEIF


def test_gleif_mapping_skips_ambiguous() -> None:
    z = gleif_zip(
        [
            ("LEI_SIEMENS_00000001", "DE0007236101"),
            ("LEI_APPLE_0000000001", "US0378331005"),
            ("LEI_APPLE_0000000002", "US0378331005"),
            ("LEI_OTHER_0000000001", "FR0000121014"),
        ]
    )
    assert gleif.lei_by_isin(z, ["DE0007236101", "US0378331005"]) == {
        "DE0007236101": "LEI_SIEMENS_00000001"
    }


def test_gleif_rejects_wrong_header() -> None:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("x.csv", "ISIN,LEI\n")
    with pytest.raises(SourceFormatError):
        gleif.lei_by_isin(buf.getvalue(), [])


# ---------------------------------------------------------------- Rohdaten


def test_rawstore_roundtrip_and_dedupe(tmp_path: Path) -> None:
    now = datetime(2026, 10, 11, tzinfo=UTC)
    a = rawstore.save(tmp_path, b"inhalt", "https://x", now)
    b = rawstore.save(tmp_path, b"inhalt", "https://y", now)
    assert a.sha256 == b.sha256 and len(list(tmp_path.glob("*.gz"))) == 1
    assert rawstore.load(tmp_path, a.sha256) == b"inhalt"


def test_rawstore_detects_corruption(tmp_path: Path) -> None:
    import gzip

    ref = rawstore.save(tmp_path, b"inhalt", "https://x", datetime(2026, 10, 11, tzinfo=UTC))
    (tmp_path / f"{ref.sha256}.gz").write_bytes(gzip.compress(b"anders"))
    with pytest.raises(ValueError, match="beschädigt"):
        rawstore.load(tmp_path, ref.sha256)


# ---------------------------------------------------------------- Ablauf


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

    def __call__(self, url: str, user_agent: str) -> bytes:
        assert "stockagent" in user_agent
        self.calls.append(url)
        if url in self.pages:
            return self.pages[url]
        if "mapping.gleif.org" in url:
            return gleif_zip([("529900T8BM49AURSDO55", "DE0007164600")])
        for name, content in self.files.items():
            if url.endswith(name):
                return content
        raise AssertionError(f"unerwartete URL {url}")


T0 = datetime(2026, 10, 11, 8, tzinfo=UTC)
FRA = [s for s in STOCKS if s[1] != "DE0007164600"]
XET = [s for s in STOCKS if s[1] in ("DE0007164600", "DE0007236101")]


def _listings(paths: Paths) -> dict[str, tuple[bool, bool, str | None]]:
    conn = store.connect(paths.db)
    rows = conn.execute("SELECT isin, listed, on_xetra, lei FROM listings").fetchall()
    conn.close()
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


def test_update_first_run(project: Paths) -> None:
    res = universe_mod.update(project, fetcher=FakeWeb(FRA, XET), now=T0)
    assert res.applied and res.stock_count == 3 and res.with_lei == 1
    rows = _listings(project)
    assert rows["DE0007164600"] == (True, True, "529900T8BM49AURSDO55")  # nur auf Xetra
    assert rows["US0378331005"] == (True, False, None)
    assert len(list(project.raw.glob("*.gz"))) == 3


def test_update_skips_when_recent(project: Paths) -> None:
    universe_mod.update(project, fetcher=FakeWeb(FRA, XET), now=T0)
    web = FakeWeb(FRA, XET)
    res = universe_mod.update(project, fetcher=web, now=T0 + timedelta(days=2))
    assert not res.applied and web.calls == [] and "aktuell genug" in res.message


def test_update_blocks_large_change_without_force(project: Paths) -> None:
    universe_mod.update(project, fetcher=FakeWeb(FRA, XET), now=T0)
    later = T0 + timedelta(days=7)
    res = universe_mod.update(project, fetcher=FakeWeb(FRA[:1], []), now=later)
    assert not res.applied and "Nicht übernommen" in res.message
    assert all(v[0] for v in _listings(project).values())  # nichts verändert

    res = universe_mod.update(project, fetcher=FakeWeb(FRA[:1], []), now=later, force=True)
    assert res.applied
    rows = _listings(project)
    assert rows["DE0007236101"][0] and not rows["US0378331005"][0]  # entfernt, aber erhalten
    assert rows["DE0007164600"][2] == "529900T8BM49AURSDO55"  # LEI bleibt erhalten


# ---------------------------------------------------------------- Prüfungen und Anzeige


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
    universe_mod.update(project, fetcher=FakeWeb(FRA, XET), now=T0)
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


def test_html_escapes_script_in_names() -> None:
    row = universe_view.ViewRow("</script><b>X", "DE0007164600", "", "DE", "", False, "", "")
    info = universe_view.ViewMeta(1, date(2026, 10, 12), "11.10.2026 08:00 UTC", 0)
    page = universe_view.to_html([row], info)
    assert "</script><b>" not in page


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
    universe_mod.update(project, fetcher=FakeWeb(FRA, XET), now=T0)
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
