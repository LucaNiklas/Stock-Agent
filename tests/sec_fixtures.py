"""Gekürzte echte SEC- und OpenFIGI-Antworten aus tests/fixtures/sec/ und eine Test-Umgebung."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from stockagent.data import store
from stockagent.paths import Paths

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures" / "sec"
AGENT = "Test Person test@example.com"

APPLE, PAGERDUTY, JPM = "0000320193", "0001568100", "0000019617"
ISIN = {APPLE: "US0378331005", PAGERDUTY: "US69553P1003", JPM: "US46625H1005"}
# Nach Abruf der Testdaten (13.10.2026), damit alle Einreichungen sichtbar sind
NOW = datetime(2026, 10, 13, 20, 0, tzinfo=UTC)


def read(name: str) -> bytes:
    return (FIX / name).read_bytes()


def project(tmp_path: Path) -> Paths:
    (tmp_path / "config").mkdir()
    for name in (
        "sources.yaml",
        "quality.yaml",
        "concept_map.yaml",
        "metrics.yaml",
        "hinweise.yaml",
    ):
        shutil.copy(ROOT / "config" / name, tmp_path / "config" / name)
    paths = Paths(tmp_path)
    conn = store.connect(paths.db)
    rows = [
        _listing("US0378331005", "APPLE INC.", "HWUPKR0MPOU8FGXBT394", "APPLE INC."),
        _listing("US69553P1003", "PAGERDUTY INC. DL-,000005", None, None),
        _listing("US46625H1005", "JPMORGAN CHASE       DL 1", None, None),
        _listing("US0000000000", "UNBEKANNT INC.", None, None),
    ]
    store.apply_snapshot(
        conn, rows, retrieved_at=NOW, source_as_of=date(2026, 10, 12), raw=[], forced=False
    )
    conn.close()
    return paths


def _listing(isin: str, name: str, lei: str | None, lei_name: str | None) -> store.ListingRow:
    return store.ListingRow(
        isin=isin,
        name=name,
        wkn="",
        mnemonic="",
        isin_country="US",
        currency="EUR",
        primary_mic="XNAS",
        on_xetra=True,
        lei=lei,
        lei_name=lei_name,
        lei_status="ISSUED" if lei else None,
        lei_plausible=True if lei else None,
        legal_country="US" if lei else None,
        hq_country="US" if lei else None,
        country="US",
        country_source="gleif" if lei else "isin",
        is_receipt=False,
        isin_valid=True,
    )


class FakeWeb:
    """Beantwortet die Adressen aus config/sources.yaml mit den Testdaten."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.posts: list[list[str]] = []

    def __call__(self, url: str, agent: str, **kw: Any) -> bytes:
        self.calls.append(url)
        if "openfigi" in url:
            isins = [j["idValue"] for j in json.loads(kw["data"])]
            self.posts.append(isins)
            answers = json.loads(read("openfigi_mapping.json"))
            by_isin = dict(
                zip(
                    ["US0378331005", "US69553P1003", "US46625H1005", "US0000000000"],
                    answers,
                    strict=True,
                )
            )
            return json.dumps([by_isin[i] for i in isins]).encode()
        assert agent == AGENT, "SEC braucht den User-Agent mit E-Mail"
        if url.endswith("company_tickers_exchange.json"):
            return read("company_tickers_exchange.json")
        for cik in (APPLE, PAGERDUTY, JPM):
            if url.endswith(f"submissions/CIK{cik}.json"):
                return read(f"submissions_{cik}.json")
            if url.endswith(f"companyfacts/CIK{cik}.json"):
                return read(f"companyfacts_{cik}.json")
        if url.endswith("000032019325000079/index.json"):
            return read("aapl_10k_index.json")
        for name in ("aapl-20250927_htm.xml", "aapl-20250927_cal.xml"):
            if url.endswith(name):
                return read(name)
        from stockagent.data.http import NotFound

        raise NotFound(f"{url}: nicht in den Testdaten")


def no_sleep(_: float) -> None:
    pass
