"""Bauschritt 2 und 3: Schema, Migration, Abschlusswerte und pit_query (HR-07)."""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from stockagent.data import store

ROOT = Path(__file__).resolve().parent.parent
ISSUER = "sec:0000000001"
RETRIEVED = datetime(2026, 10, 13, tzinfo=UTC)


def fact(value: str, published: datetime, acc: str, **kw: object) -> store.FactRow:
    data: dict[str, object] = {
        "issuer_id": ISSUER,
        "concept": "us-gaap:Revenues",
        "value": Decimal(value),
        "unit": "monetary",
        "unit_raw": "USD",
        "currency": "USD",
        "period_start": date(2023, 1, 1),
        "period_end": date(2023, 12, 31),
        "fiscal_year": 2023,
        "fiscal_period": "FY",
        "form": "10-K",
        "accession": acc,
        "published_at": published,
        "source_type": "xbrl",
        "xbrl_context": f"{acc}|us-gaap:Revenues",
        "raw_sha256": "abc",
        "retrieved_at": RETRIEVED,
    }
    data.update(kw)
    return store.FactRow(**data)  # type: ignore[arg-type]


def t(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, 21, tzinfo=UTC)


V2024 = fact("100000000", t(2024, 2, 20), "0000000001-24-000001")
V2025 = fact("100000000", t(2025, 2, 20), "0000000001-25-000001")  # Wiederholung im Folgejahr
V2025_R = fact("90000000", t(2025, 8, 1), "0000000001-25-000009", form="10-K/A")  # Restatement


@pytest.fixture
def conn(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    c = store.connect(tmp_path / "t.duckdb")
    store.replace_facts(c, ISSUER, [V2025_R, V2024, V2025], [])
    return c


def test_pit_query_hides_future_and_applies_restatement_from_its_date(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    assert store.pit_query(conn, as_of=t(2024, 2, 19), issuer_id=ISSUER) == []
    vorher = store.pit_query(conn, as_of=t(2025, 7, 31), issuer_id=ISSUER)
    assert [f.value for f in vorher] == [Decimal(100000000)]
    assert vorher[0].accession == V2024.accession  # erste Veröffentlichung bleibt maßgeblich
    nachher = store.pit_query(conn, as_of=t(2025, 8, 2), issuer_id=ISSUER)
    assert [(f.value, f.form) for f in nachher] == [(Decimal(90000000), "10-K/A")]


def test_superseded_by_marks_restatement(conn: duckdb.DuckDBPyConnection) -> None:
    pairs = store.restatements(conn, as_of=t(2026, 1, 1), issuer_id=ISSUER)
    assert len(pairs) == 1
    alt, neu = pairs[0]
    assert alt.accession == V2024.accession and neu.accession == V2025_R.accession
    assert store.restatements(conn, as_of=t(2025, 7, 31), issuer_id=ISSUER) == []


def test_first_version_and_single_filing(conn: duckdb.DuckDBPyConnection) -> None:
    erste = store.pit_query(conn, as_of=t(2026, 1, 1), issuer_id=ISSUER, fassung="erste")
    assert [f.accession for f in erste] == [V2024.accession]
    nur = store.pit_query(
        conn,
        as_of=t(2026, 1, 1),
        issuer_id=ISSUER,
        fassung="einreichung",
        accession=V2025.accession,
    )
    assert [f.accession for f in nur] == [V2025.accession]
    with pytest.raises(ValueError):
        store.pit_query(conn, as_of=t(2026, 1, 1), issuer_id=ISSUER, fassung="einreichung")


def test_pit_query_needs_timezone(conn: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(ValueError):
        store.pit_query(conn, as_of=datetime(2026, 1, 1), issuer_id=ISSUER)


def test_replace_facts_replaces_issuer_rows_only(conn: duckdb.DuckDBPyConnection) -> None:
    andere = fact("5", t(2024, 1, 1), "0000000002-24-000001", issuer_id="sec:0000000002")
    store.replace_facts(conn, "sec:0000000002", [andere], [])
    store.replace_facts(conn, ISSUER, [V2024], [])
    assert len(store.pit_query(conn, as_of=t(2026, 1, 1), issuer_id="sec:0000000002")) == 1
    with pytest.raises(ValueError, match="anderen Emittenten"):
        store.replace_facts(conn, ISSUER, [andere], [])


def test_no_query_without_as_of() -> None:
    """HR-07: `facts` wird nur in store.py gelesen, und pit_query verlangt as_of."""
    sig = inspect.signature(store.pit_query)
    assert sig.parameters["as_of"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["as_of"].default is inspect.Parameter.empty
    offenders = []
    for path in (ROOT / "src" / "stockagent").rglob("*.py"):
        if path.name == "store.py":
            continue
        for node in ast.walk(ast.parse(path.read_text("utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = " ".join(node.value.upper().split())
                if "FROM FACTS" in text or "JOIN FACTS" in text:
                    offenders.append(str(path))
    assert offenders == []


def test_migration_from_schema_3_keeps_listings(tmp_path: Path) -> None:
    db = tmp_path / "alt.duckdb"
    c = duckdb.connect(str(db))
    c.execute("CREATE TABLE meta (key VARCHAR PRIMARY KEY, value VARCHAR NOT NULL)")
    c.execute("INSERT INTO meta VALUES ('schema_version', '3')")
    c.execute("CREATE TABLE listings (isin VARCHAR PRIMARY KEY, name VARCHAR)")
    c.execute("INSERT INTO listings VALUES ('US0378331005', 'APPLE INC.')")
    c.close()
    conn = store.connect(db)
    assert conn.execute("SELECT name FROM listings").fetchall() == [("APPLE INC.",)]
    version = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    assert version == (str(store.SCHEMA_VERSION),)
    rows = conn.execute("SELECT table_name FROM information_schema.tables").fetchall()
    tables = {r[0] for r in rows}
    assert {"isin_cik", "issuers", "documents", "facts", "dq_flags"} <= tables
    assert {"metrics", "metric_runs", "hinweise"} <= tables


def test_migration_from_schema_4_adds_metric_tables(tmp_path: Path) -> None:
    db = tmp_path / "alt.duckdb"
    c = duckdb.connect(str(db))
    c.execute("CREATE TABLE meta (key VARCHAR PRIMARY KEY, value VARCHAR NOT NULL)")
    c.execute("INSERT INTO meta VALUES ('schema_version', '4')")
    c.execute("CREATE TABLE facts (fact_id BIGINT, issuer_id VARCHAR)")
    c.execute("INSERT INTO facts VALUES (1, 'sec:0000320193')")
    c.close()
    conn = store.connect(db)
    assert conn.execute("SELECT issuer_id FROM facts").fetchall() == [("sec:0000320193",)]
    assert conn.execute("SELECT count(*) FROM metrics").fetchone() == (0,)
    assert conn.execute("SELECT count(*) FROM hinweise").fetchone() == (0,)


def test_unknown_old_schema_still_refused(tmp_path: Path) -> None:
    db = tmp_path / "alt.duckdb"
    c = duckdb.connect(str(db))
    c.execute("CREATE TABLE meta (key VARCHAR PRIMARY KEY, value VARCHAR NOT NULL)")
    c.execute("INSERT INTO meta VALUES ('schema_version', '2')")
    c.close()
    with pytest.raises(store.SchemaOutdated):
        store.connect(db)


def test_empty_writes_are_fine(conn: duckdb.DuckDBPyConnection) -> None:
    store.save_isin_cik(conn, [], RETRIEVED)
    store.replace_dq_flags(conn, ISSUER, [], RETRIEVED)
    store.replace_facts(conn, "sec:0000000003", [], [])
