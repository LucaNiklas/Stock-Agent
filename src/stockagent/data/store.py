"""DuckDB-Ablage (SPEC 7.6, 7.7). In Schritt 1 nur Universum und Abrufprotokoll.

`pit_query(as_of=...)` für Abschlussdaten folgt in Schritt 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS universe_snapshots (
    snapshot_id   INTEGER PRIMARY KEY,
    retrieved_at  TIMESTAMP NOT NULL,
    source_as_of  DATE NOT NULL,
    frankfurt_sha VARCHAR NOT NULL,
    xetra_sha     VARCHAR NOT NULL,
    gleif_sha     VARCHAR,
    stock_count   INTEGER NOT NULL,
    forced        BOOLEAN NOT NULL
);
CREATE TABLE IF NOT EXISTS listings (
    isin            VARCHAR PRIMARY KEY,
    name            VARCHAR NOT NULL,
    wkn             VARCHAR,
    mnemonic        VARCHAR,
    isin_country    VARCHAR,
    currency        VARCHAR,
    primary_mic     VARCHAR,
    on_xetra        BOOLEAN NOT NULL,
    lei             VARCHAR,
    isin_valid      BOOLEAN NOT NULL,
    listed          BOOLEAN NOT NULL,
    first_seen      DATE NOT NULL,
    last_seen       DATE NOT NULL,
    snapshot_id     INTEGER NOT NULL
);
"""


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
    isin_valid: bool


def connect(path: Path) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(path))
    conn.execute(SCHEMA)
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


def apply_snapshot(
    conn: duckdb.DuckDBPyConnection,
    rows: list[ListingRow],
    *,
    retrieved_at: datetime,
    source_as_of: date,
    frankfurt_sha: str,
    xetra_sha: str,
    gleif_sha: str | None,
    forced: bool,
) -> int:
    """Schreibt einen neuen Stand. Fehlende Titel bleiben mit listed = false erhalten."""
    conn.execute("BEGIN")
    try:
        row = conn.execute("SELECT coalesce(max(snapshot_id), 0) + 1 FROM universe_snapshots")
        snapshot_id = int(row.fetchone()[0])  # type: ignore[index]
        conn.execute(
            "INSERT INTO universe_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                snapshot_id,
                _utc_naive(retrieved_at),
                source_as_of,
                frankfurt_sha,
                xetra_sha,
                gleif_sha,
                len(rows),
                forced,
            ],
        )
        conn.execute("CREATE TEMP TABLE incoming AS SELECT * FROM listings LIMIT 0")
        conn.executemany(
            "INSERT INTO incoming VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, true, ?, ?, ?)",
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
                    r.isin_valid,
                    source_as_of,
                    source_as_of,
                    snapshot_id,
                ]
                for r in rows
            ],
        )
        conn.execute(
            """
            INSERT INTO listings SELECT * FROM incoming
            ON CONFLICT (isin) DO UPDATE SET
                name = excluded.name, wkn = excluded.wkn, mnemonic = excluded.mnemonic,
                isin_country = excluded.isin_country, currency = excluded.currency,
                primary_mic = excluded.primary_mic, on_xetra = excluded.on_xetra,
                lei = coalesce(excluded.lei, listings.lei), isin_valid = excluded.isin_valid,
                listed = true, last_seen = excluded.last_seen, snapshot_id = excluded.snapshot_id
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
