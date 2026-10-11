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
from stockagent.core.identifiers import (
    change_exceeds,
    choose_country,
    is_depositary_receipt,
    isin_is_valid,
    names_plausibly_match,
)
from stockagent.data import rawstore, store
from stockagent.data.sources import deutsche_boerse, gleif
from stockagent.data.sources.deutsche_boerse import SourceFormatError
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


def test_html_escapes_script_in_names() -> None:
    row = universe_view.ViewRow(
        "</script><b>X",
        "DE0007164600",
        "",
        "DE",
        "nur ISIN (unsicher)",
        "",
        "Aktie",
        "",
        False,
        "",
        "",
    )
    info = universe_view.ViewMeta(1, date(2026, 10, 12), "11.10.2026 08:00 UTC", 0, 0)
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


# ---------------------------------------------------------------- Länder und LEI-Plausibilität


@pytest.mark.parametrize(
    ("listing", "legal", "match"),
    [
        ("SIEMENS AG NA O.N.", "Siemens Aktiengesellschaft", True),
        ("BAYER ADR /1/4", "Bayer Aktiengesellschaft", True),
        ("S.ENER.ELEC.SP.GDR REGS 1", "SOCIETATEA ENERGETICĂ ELECTRICA S.A.", True),
        ("KAZAKHTELE.ADR1/15/KT1000", "KAZAKHTELECOM JSC", True),
        ("IBM CORP.", "International Business Machines Corporation", True),
        ("MERCURY GENL CORP.", "GRAND PEAK CAPITAL CORP.", False),
        ("ALLIANZ SE NA O.N.", "Allianz SE", True),
        ("SAP SE O.N.", "Siemens Aktiengesellschaft", False),
        ("NU HLDGS  CL.A DL-,000066", "Nu Holdings Ltd.", True),
        ("8X8               DL-,001", "8X8, INC.", True),
        ("3I GROUP PLC   LS-,738636", "3I GROUP PLC", True),
        ("A.P.MOELL.-M.NAM B DK1000", "A.P. MØLLER - MÆRSK A/S", True),
        ("ASAHI GROUP HOLDINGS LTD.", "アサヒグループホールディングス株式会社", False),
        ("ASAHI GROUP HOLDINGS LTD.", "Asahi Group Holdings,Ltd.", True),
        ("CODEXIS INC.       DL-,01", "Cedexis Inc.", False),
        ("STROEER (UNSP.ARD)/4/1", "Ströer SE & Co. KGaA", True),
        ("STROER SE + CO. KGAA", "Ströer SE & Co. KGaA", True),
    ],
)
def test_names_plausibly_match(listing: str, legal: str, match: bool) -> None:
    assert names_plausibly_match(listing, legal) is match


def test_choose_country() -> None:
    # ADR: ISIN-Land US sagt nichts, Hauptsitz laut GLEIF gilt
    assert choose_country("US", "DE", "DE", True, receipt=True) == ("DE", "gleif")
    # Xiaomi: Sitz KY wie ISIN, Hauptsitz CN
    assert choose_country("KY", "KY", "CN", True, receipt=False) == ("CN", "gleif")
    # Steris: irische ISIN, LEI der alten britischen Gesellschaft
    assert choose_country("IE", "GB", "GB", True, receipt=False) == ("IE", "konflikt")
    assert choose_country("US", "CA", "CA", False, receipt=False) == ("US", "isin")
    assert choose_country("KY", None, None, False, receipt=False) == ("KY", "isin")


@pytest.mark.parametrize(
    ("name", "receipt"),
    [
        ("BAYER ADR /1/4", True),
        ("PHARMING GRP SP. ADRS", True),
        ("LIFE360 INC.CDIS/3 O.N.", True),
        ("WALT DISNEY CO. CDR O.N.", True),
        ("AUTOLIV SDR/1 DL-,01", True),
        ("ASML HOLDING NY    EO-,09", True),
        ("HARMONY GD MNG ADRRC,-50", True),
        ("KESORAM IND.LTD GDRREGS/1", True),
        ("NIPPON YUSEN K.K.SP.DR1/5", True),
        ("SIEMENS AG NA O.N.", False),
        ("ADIDAS AG NA O.N.", False),
        ("CADELER A/S DK 1", False),
        ("NYRSTAR", False),
        ("RECKITT BENCKISER ADRO.N", True),
        ("DOWNER EDI LTD.UNSP. 2", True),
        ("ADRIATIC METALS PLC", False),
    ],
)
def test_is_depositary_receipt(name: str, receipt: bool) -> None:
    assert is_depositary_receipt(name) is receipt


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


def test_entity_urls_batches() -> None:
    urls = gleif.entity_urls("https://api.example/lei", [f"L{i:019d}" for i in range(450)], 200)
    assert len(urls) == 3 and urls[0].count(",") == 199 and urls[2].count(",") == 49


def test_parse_entities_rejects_unknown_layout() -> None:
    with pytest.raises(SourceFormatError):
        gleif.parse_entities(b'{"data": [{"id": "X"}]}')


# ---------------------------------------------------------------- Aufräumregel GLEIF


def test_prune_keeps_recent_and_foreign(tmp_path: Path) -> None:
    now = datetime(2026, 10, 11, tzinfo=UTC)
    old = rawstore.save(tmp_path, b"alt", "https://mapping.gleif.org/x", now)
    new = rawstore.save(tmp_path, b"neu", "https://mapping.gleif.org/x", now)
    other = rawstore.save(tmp_path, b"boerse", "https://www.cashmarket.deutsche-boerse.com/x", now)
    removed = rawstore.prune(tmp_path, ("https://mapping.gleif.org",), keep={new.sha256})
    assert removed == [old.sha256]
    left = {p.stem for p in tmp_path.glob("*.gz")}
    assert left == {new.sha256, other.sha256}


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


def test_parse_entities_collects_other_names() -> None:
    raw = (
        b'{"data": [{"id": "L1", "attributes": {"entity": '
        b'{"legalName": {"name": "\\u30a2\\u30b5\\u30d2"},'
        b' "legalAddress": {"country": "JP"}, "headquartersAddress": {"country": "JP"},'
        b' "status": "ACTIVE", "otherNames": [{"name": "Asahi Group Holdings,Ltd.",'
        b' "type": "ALTERNATIVE_LANGUAGE_LEGAL_NAME"}], "transliteratedOtherNames": null}}}]}'
    )
    ent = gleif.parse_entities(raw)["L1"]
    assert ent.all_names[1] == "Asahi Group Holdings,Ltd."
    assert any(names_plausibly_match("ASAHI GROUP HOLDINGS LTD.", n) for n in ent.all_names)


def test_html_header_keeps_commas() -> None:
    """Regression: .replace auf verketteten f-Strings hat alle Kommas zu Punkten gemacht."""
    info = universe_view.ViewMeta(14509, date(2026, 10, 12), "11.10.2026 08:00 UTC", 2, 8102)
    page = universe_view.to_html([], info)
    assert "14.509 Aktien" in page and "8.102 Aktien" in page
    assert "(Deutsche Börse, Stand 12.10.2026, abgerufen" in page
