"""DuckDB-Ablage (SPEC 7.6, 7.7). In Schritt 1 nur Universum und Abrufprotokoll.

`pit_query(as_of=...)` für Abschlussdaten folgt in Schritt 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

SCHEMA_VERSION = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key VARCHAR PRIMARY KEY, value VARCHAR NOT NULL);
CREATE TABLE IF NOT EXISTS universe_snapshots (
    snapshot_id   INTEGER PRIMARY KEY,
    retrieved_at  TIMESTAMP NOT NULL,   -- naives UTC
    source_as_of  DATE NOT NULL,
    stock_count   INTEGER NOT NULL,
    forced        BOOLEAN NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshot_raw (
    snapshot_id INTEGER NOT NULL,
    kind        VARCHAR NOT NULL,       -- frankfurt, xetra, gleif_mapping, gleif_entities
    sha256      VARCHAR NOT NULL,
    url         VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS listings (
    isin            VARCHAR PRIMARY KEY,
    name            VARCHAR NOT NULL,
    wkn             VARCHAR,
    mnemonic        VARCHAR,
    isin_country    VARCHAR NOT NULL,
    currency        VARCHAR,
    primary_mic     VARCHAR,
    on_xetra        BOOLEAN NOT NULL,
    lei             VARCHAR,
    lei_name        VARCHAR,
    lei_status      VARCHAR,
    lei_plausible   BOOLEAN,            -- NULL ohne LEI
    legal_country   VARCHAR,            -- Rechtsordnung laut GLEIF (jurisdiction)
    hq_country      VARCHAR,
    country         VARCHAR NOT NULL,   -- angezeigtes Land (Hauptsitz)
    country_source  VARCHAR NOT NULL,   -- gleif, isin oder konflikt
    is_receipt      BOOLEAN NOT NULL,   -- Hinterlegungsschein (ADR, GDR, ...)
    isin_valid      BOOLEAN NOT NULL,
    listed          BOOLEAN NOT NULL,
    first_seen      DATE NOT NULL,
    last_seen       DATE NOT NULL,
    snapshot_id     INTEGER NOT NULL
);
"""

_COLUMNS = (
    "isin, name, wkn, mnemonic, isin_country, currency, primary_mic, on_xetra, lei, lei_name, "
    "lei_status, lei_plausible, legal_country, hq_country, country, country_source, is_receipt, "
    "isin_valid"
)


class SchemaOutdated(RuntimeError):
    pass


@dataclass(frozen=True)
class ListingRow:
    isin: str
    name: str
    wkn: str
    mnemonic: str
    isin_country: str
    currency: str
    primary_mic: str
    on_xetra: bool
    lei: str | None
    lei_name: str | None
    lei_status: str | None
    lei_plausible: bool | None
    legal_country: str | None
    hq_country: str | None
    country: str
    country_source: str
    is_receipt: bool
    isin_valid: bool


@dataclass(frozen=True)
class RawUse:
    kind: str
    sha256: str
    url: str


def connect(path: Path) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not path.exists()
    conn = duckdb.connect(str(path))
    if not fresh:
        tables = {
            r[0]
            for r in conn.execute("SELECT table_name FROM information_schema.tables").fetchall()
        }
        version = None
        if "meta" in tables:
            row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
            version = int(row[0]) if row else None
        if tables and version != SCHEMA_VERSION:
            conn.close()
            raise SchemaOutdated(
                f"Datenbank {path} hat Schema {version}, erwartet {SCHEMA_VERSION}. "
                "Datei löschen und mit 'stockagent universe update --refresh' neu aufbauen."
            )
    conn.execute(SCHEMA)
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)", [str(SCHEMA_VERSION)])
    return conn


def last_stock_count(conn: duckdb.DuckDBPyConnection) -> int | None:
    row = conn.execute(
        "SELECT stock_count FROM universe_snapshots ORDER BY snapshot_id DESC LIMIT 1"
    ).fetchone()
    return None if row is None else int(row[0])


def _utc_naive(ts: datetime) -> datetime:
    """DuckDB rechnet Zeiten mit Zeitzone in die lokale Zeit um. Gespeichert wird naives UTC."""
    if ts.tzinfo is None:
        raise ValueError("Zeitstempel ohne Zeitzone")
    return ts.astimezone(UTC).replace(tzinfo=None)


def last_retrieved_at(conn: duckdb.DuckDBPyConnection) -> datetime | None:
    row = conn.execute("SELECT max(retrieved_at) FROM universe_snapshots").fetchone()
    return None if row is None or row[0] is None else row[0].replace(tzinfo=UTC)


def is_listed(conn: duckdb.DuckDBPyConnection, isin: str) -> bool:
    row = conn.execute("SELECT listed FROM listings WHERE isin = ?", [isin]).fetchone()
    return bool(row and row[0])


def raw_in_recent_snapshots(
    conn: duckdb.DuckDBPyConnection, kinds: tuple[str, ...], keep_snapshots: int
) -> set[str]:
    """Hashes der Rohdateien dieser Arten, die einer der letzten keep_snapshots Stände nutzt."""
    rows = conn.execute(
        f"""
        SELECT DISTINCT sha256 FROM snapshot_raw
        WHERE kind IN ({",".join("?" * len(kinds))}) AND snapshot_id IN (
            SELECT snapshot_id FROM universe_snapshots ORDER BY snapshot_id DESC LIMIT ?)
        """,
        [*kinds, keep_snapshots],
    ).fetchall()
    return {r[0] for r in rows}


def apply_snapshot(
    conn: duckdb.DuckDBPyConnection,
    rows: list[ListingRow],
    *,
    retrieved_at: datetime,
    source_as_of: date,
    raw: list[RawUse],
    forced: bool,
) -> int:
    """Schreibt einen neuen Stand. Fehlende Titel bleiben mit listed = false erhalten."""
    conn.execute("BEGIN")
    try:
        row = conn.execute("SELECT coalesce(max(snapshot_id), 0) + 1 FROM universe_snapshots")
        snapshot_id = int(row.fetchone()[0])  # type: ignore[index]
        conn.execute(
            "INSERT INTO universe_snapshots VALUES (?, ?, ?, ?, ?)",
            [snapshot_id, _utc_naive(retrieved_at), source_as_of, len(rows), forced],
        )
        conn.executemany(
            "INSERT INTO snapshot_raw VALUES (?, ?, ?, ?)",
            [[snapshot_id, r.kind, r.sha256, r.url] for r in raw],
        )
        conn.execute("CREATE TEMP TABLE incoming AS SELECT * FROM listings LIMIT 0")
        placeholders = ", ".join("?" * 18)
        conn.executemany(
            f"INSERT INTO incoming ({_COLUMNS}, listed, first_seen, last_seen, snapshot_id) "
            f"VALUES ({placeholders}, true, ?, ?, ?)",
            [
                [
                    r.isin,
                    r.name,
                    r.wkn,
                    r.mnemonic,
                    r.isin_country,
                    r.currency,
                    r.primary_mic,
                    r.on_xetra,
                    r.lei,
                    r.lei_name,
                    r.lei_status,
                    r.lei_plausible,
                    r.legal_country,
                    r.hq_country,
                    r.country,
                    r.country_source,
                    r.is_receipt,
                    r.isin_valid,
                    source_as_of,
                    source_as_of,
                    snapshot_id,
                ]
                for r in rows
            ],
        )
        updates = ", ".join(f"{c} = excluded.{c}" for c in _COLUMNS.split(", ") if c != "isin")
        conn.execute(
            f"""
            INSERT INTO listings SELECT * FROM incoming
            ON CONFLICT (isin) DO UPDATE SET {updates}, listed = true,
                last_seen = excluded.last_seen, snapshot_id = excluded.snapshot_id
            """
        )
        conn.execute(
            "UPDATE listings SET listed = false WHERE isin NOT IN (SELECT isin FROM incoming)"
        )
        conn.execute("DROP TABLE incoming")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return snapshot_id
