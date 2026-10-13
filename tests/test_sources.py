"""Bauschritt 1: Lesen der Quellen Deutsche Börse und GLEIF, Rohablage, HTML-Anzeige."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from stockagent.core.identifiers import (
    names_plausibly_match,
)
from stockagent.data import rawstore
from stockagent.data.sources import deutsche_boerse, gleif
from stockagent.data.sources.deutsche_boerse import SourceFormatError
from stockagent.report import universe_view
from tests.universe_fixtures import (
    STOCKS,
    download_page,
    gleif_zip,
    instrument_csv,
)


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


def test_entity_urls_batches() -> None:
    urls = gleif.entity_urls("https://api.example/lei", [f"L{i:019d}" for i in range(450)], 200)
    assert len(urls) == 3 and urls[0].count(",") == 199 and urls[2].count(",") == 49


def test_parse_entities_rejects_unknown_layout() -> None:
    with pytest.raises(SourceFormatError):
        gleif.parse_entities(b'{"data": [{"id": "X"}]}')


def test_prune_keeps_recent_and_foreign(tmp_path: Path) -> None:
    now = datetime(2026, 10, 11, tzinfo=UTC)
    old = rawstore.save(tmp_path, b"alt", "https://mapping.gleif.org/x", now)
    new = rawstore.save(tmp_path, b"neu", "https://mapping.gleif.org/x", now)
    other = rawstore.save(tmp_path, b"boerse", "https://www.cashmarket.deutsche-boerse.com/x", now)
    removed = rawstore.prune(tmp_path, ("https://mapping.gleif.org",), keep={new.sha256})
    assert removed == [old.sha256]
    left = {p.stem for p in tmp_path.glob("*.gz")}
    assert left == {new.sha256, other.sha256}


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
