"""DuckDB-Ablage (SPEC 7.6, 7.7).

Schritt 1: Universum und Abrufprotokoll. Schritt 2: Zuordnung ISIN zu CIK, Emittenten,
Dokumente, Abschlusswerte (`facts`) und Datenqualitäts-Flags. Abschlusswerte werden nur über
`pit_query(as_of=...)` gelesen (HR-07). Schritt 3: Kennzahlen mit Rechenweg (`metrics`), Läufe
(`metric_runs`) und Hinweise an die Agenten (`hinweise`).
"""

from __future__ import annotations

import csv
import json
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import duckdb

from stockagent.core import pit
from stockagent.core.hinweise import Hinweis, Kennzahlwert

SCHEMA_VERSION = 6

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

# Schritt 2 (Schema 4). issuer_id ist `sec:<CIK mit 10 Ziffern>` für SEC-Melder, später
# `lei:<LEI>` für Emittenten ohne CIK (ESEF, Schritt 7). Die Zusammenführung mehrerer Kennungen
# eines Unternehmens folgt über lei und cik in `issuers`.
SCHEMA_V4 = """
CREATE TABLE IF NOT EXISTS isin_cik (
    isin        VARCHAR PRIMARY KEY,
    cik         VARCHAR,                -- 10 Ziffern, NULL wenn nicht sicher zugeordnet
    ticker      VARCHAR,
    method      VARCHAR NOT NULL,       -- openfigi, name, manuell, keine
    status      VARCHAR NOT NULL,       -- zugeordnet, unsicher, keine
    detail      VARCHAR NOT NULL,
    checked_at  TIMESTAMP NOT NULL,     -- naives UTC
    figi_name   VARCHAR                 -- Name laut OpenFIGI, für die Neubewertung
);
ALTER TABLE isin_cik ADD COLUMN IF NOT EXISTS figi_name VARCHAR;
CREATE TABLE IF NOT EXISTS issuers (
    issuer_id               VARCHAR PRIMARY KEY,
    lei                     VARCHAR,
    cik                     VARCHAR,
    name                    VARCHAR NOT NULL,
    country                 VARCHAR,    -- Land der Geschäftsadresse (ISO), soweit ableitbar
    sector_sic              VARCHAR,
    sic_description         VARCHAR,
    sector_nace             VARCHAR,
    accounting_standard     VARCHAR,
    fiscal_year_end         VARCHAR,    -- MMDD laut SEC
    state_of_incorporation  VARCHAR,
    business_address        VARCHAR,
    business_region         VARCHAR,    -- Bundesstaat (US) oder Länderkennung der SEC
    entity_type             VARCHAR,
    filer_category          VARCHAR,
    source                  VARCHAR NOT NULL,
    source_sha256           VARCHAR NOT NULL,
    retrieved_at            TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    doc_id        VARCHAR PRIMARY KEY,  -- sec:<Accession>
    doc_hash      VARCHAR,              -- SHA-256 der abgelegten Datei, falls geladen
    issuer_id     VARCHAR NOT NULL,
    doc_type      VARCHAR NOT NULL,     -- Formular, etwa 10-K, 10-Q, 20-F
    period_end    DATE,
    published_at  TIMESTAMP NOT NULL,
    retrieved_at  TIMESTAMP NOT NULL,
    source_url    VARCHAR NOT NULL,
    language      VARCHAR,
    pages         INTEGER
);
CREATE SEQUENCE IF NOT EXISTS fact_seq;
CREATE TABLE IF NOT EXISTS facts (
    fact_id            BIGINT PRIMARY KEY DEFAULT nextval('fact_seq'),
    issuer_id          VARCHAR NOT NULL,
    concept            VARCHAR NOT NULL,    -- mit Präfix, etwa us-gaap:Assets
    internal_metric    VARCHAR,
    value              DECIMAL(38, 10) NOT NULL,
    unit               VARCHAR NOT NULL,    -- monetary, shares, per_share, pure
    unit_raw           VARCHAR NOT NULL,    -- Einheit laut Quelle, etwa USD/shares
    scale              INTEGER NOT NULL,
    currency           VARCHAR,
    period_start       DATE,
    period_end         DATE NOT NULL,
    fiscal_year        INTEGER,
    fiscal_period      VARCHAR,
    form               VARCHAR,
    accession          VARCHAR NOT NULL,
    published_at       TIMESTAMP NOT NULL,  -- naives UTC
    source_type        VARCHAR NOT NULL,
    doc_id             VARCHAR,
    page               INTEGER,
    xbrl_context       VARCHAR,
    extraction_run_id  VARCHAR,
    raw_sha256         VARCHAR NOT NULL,
    retrieved_at       TIMESTAMP NOT NULL,
    superseded_by      BIGINT
);
CREATE INDEX IF NOT EXISTS facts_issuer ON facts (issuer_id, concept);
CREATE TABLE IF NOT EXISTS dq_flags (
    issuer_id    VARCHAR NOT NULL,
    check_id     VARCHAR NOT NULL,     -- DQ-01 bis DQ-08 nach SPEC 3.2
    severity     VARCHAR NOT NULL,     -- info, warnung, stopp
    period_end   DATE,
    concept      VARCHAR,
    detail       VARCHAR NOT NULL,
    trace_json   VARCHAR,
    checked_at   TIMESTAMP NOT NULL
);
"""

SCHEMA_V5 = """
CREATE TABLE IF NOT EXISTS metric_runs (
    run_id               VARCHAR PRIMARY KEY,  -- metrics:<issuer_id>:<as_of>
    issuer_id            VARCHAR NOT NULL,
    as_of                TIMESTAMP NOT NULL,   -- Datenstand (naives UTC), HR-07
    stichtag             DATE,                 -- letztes Geschäftsjahresende im Datenstand
    methodology_version  VARCHAR NOT NULL,
    computed_at          TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS metrics (
    run_id           VARCHAR NOT NULL,
    issuer_id        VARCHAR NOT NULL,
    metric_id        VARCHAR NOT NULL,
    metric_version   VARCHAR NOT NULL,
    statistik        VARCHAR NOT NULL,     -- wert (je Geschäftsjahr) oder Trend nach SPEC 3.4
    period_end       DATE NOT NULL,
    value            VARCHAR,              -- Decimal als Text, ungerundet. NULL = unknown
    grund            VARCHAR,              -- Grund bei unknown
    ungereimtheit    VARCHAR,              -- INC-15, wenn ein Prüfpunkt stoppte
    warnungen_json   VARCHAR NOT NULL,
    vermerke_json    VARCHAR NOT NULL,     -- Herkunftshinweise, etwa abgeleitetes EBIT
    -- Vollständiger Rechenweg mit allen Eingaben und Quellen (SPEC 12.7, HR-12), nur für die
    -- Jahreswerte des letzten Geschäftsjahres. Vorjahre und Trends speichern nur den Wert. Ihr
    -- Rechenweg ergibt sich zum selben Datenstand jederzeit gleich neu (`metrics show --jahr`,
    -- `--trend`)
    calc_trace_json  VARCHAR,
    computed_at      TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS metrics_issuer ON metrics (issuer_id, metric_id);
CREATE TABLE IF NOT EXISTS hinweise (
    run_id       VARCHAR NOT NULL,
    issuer_id    VARCHAR NOT NULL,
    regel        VARCHAR NOT NULL,     -- H-01 bis H-09 aus config/hinweise.yaml
    an_agent     VARCHAR NOT NULL,
    abteilung    VARCHAR NOT NULL,
    anlass       VARCHAR NOT NULL,
    metric_id    VARCHAR,
    period_end   DATE,
    detail       VARCHAR NOT NULL,
    status       VARCHAR NOT NULL,     -- offen, ab Schritt 6 auch beauftragt, erledigt
    erstellt_at  TIMESTAMP NOT NULL
);
"""

SCHEMA_V6 = """
CREATE TABLE IF NOT EXISTS price_symbols (
    isin           VARCHAR PRIMARY KEY,
    symbol         VARCHAR,              -- Yahoo-Symbol, NULL wenn nicht sicher zugeordnet
    exch_code      VARCHAR,              -- Bloomberg-Börsenkürzel laut OpenFIGI
    method         VARCHAR NOT NULL,     -- openfigi, manuell, keine
    status         VARCHAR NOT NULL,     -- zugeordnet, unsicher, keine
    detail         VARCHAR NOT NULL,
    quelle_name    VARCHAR,              -- Name laut Yahoo, für die Prüfung
    waehrung       VARCHAR,              -- wie geliefert, etwa GBp für Pence
    boerse         VARCHAR,
    warnungen_json VARCHAR NOT NULL,     -- Prüfungen des letzten Abrufs
    checked_at     TIMESTAMP NOT NULL,   -- naives UTC
    retrieved_at   TIMESTAMP             -- letzter Kursabruf
);
CREATE TABLE IF NOT EXISTS prices (
    isin              VARCHAR NOT NULL,
    date              DATE NOT NULL,        -- Handelstag an der Börse
    close             VARCHAR NOT NULL,     -- Decimal als Text, um Splits bereinigt
    adj_close         VARCHAR,              -- um Splits und Dividenden bereinigt
    volume            BIGINT,
    currency          VARCHAR,
    symbol            VARCHAR NOT NULL,
    source            VARCHAR NOT NULL,     -- yahoo
    raw_sha256        VARCHAR NOT NULL,
    retrieved_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (isin, date, source)
);
CREATE TABLE IF NOT EXISTS price_events (
    isin          VARCHAR NOT NULL,
    date          DATE NOT NULL,
    kind          VARCHAR NOT NULL,     -- split, dividende
    value         VARCHAR,              -- Dividende je Aktie
    numerator     VARCHAR,              -- Split 4:1: 4
    denominator   VARCHAR,              -- Split 4:1: 1
    currency      VARCHAR,
    symbol        VARCHAR NOT NULL,
    source        VARCHAR NOT NULL,
    raw_sha256    VARCHAR NOT NULL,
    PRIMARY KEY (isin, date, kind, source)
);
"""

# Schemaversionen, aus denen ohne Datenverlust aufgerüstet wird.
_MIGRATABLE = {3, 4, 5}

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
        if tables and version != SCHEMA_VERSION and version not in _MIGRATABLE:
            conn.close()
            raise SchemaOutdated(
                f"Datenbank {path} hat Schema {version}, erwartet {SCHEMA_VERSION}. "
                "Datei löschen und mit 'stockagent universe update --refresh' neu aufbauen."
            )
    conn.execute(SCHEMA)
    conn.execute(SCHEMA_V4)
    _verwerfe_vorfassung_metrics(conn)
    conn.execute(SCHEMA_V5)
    conn.execute(SCHEMA_V6)
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)", [str(SCHEMA_VERSION)])
    return conn


def _verwerfe_vorfassung_metrics(conn: duckdb.DuckDBPyConnection) -> None:
    """Die Tabelle `metrics` aus der Entwicklungsfassung von Schema 5 (mit `inputs_json`) wird
    verworfen. Sie enthält nur Rechenergebnisse, `metrics update` erzeugt sie neu."""
    spalten = {
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'metrics'"
        ).fetchall()
    }
    if "inputs_json" in spalten:
        conn.execute("DROP TABLE metrics")


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
        if raw:
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


# ------------------------------------------------------------------ Schritt 2: SEC-Daten


@dataclass(frozen=True)
class IsinCik:
    isin: str
    cik: str | None
    ticker: str | None
    method: str
    status: str
    detail: str
    figi_name: str | None = None


def save_isin_cik(conn: duckdb.DuckDBPyConnection, rows: list[IsinCik], now: datetime) -> None:
    if not rows:
        return
    conn.executemany(
        "INSERT OR REPLACE INTO isin_cik "
        "(isin, cik, ticker, method, status, detail, checked_at, figi_name) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            [r.isin, r.cik, r.ticker, r.method, r.status, r.detail, _utc_naive(now), r.figi_name]
            for r in rows
        ],
    )


def load_isin_cik(conn: duckdb.DuckDBPyConnection) -> dict[str, IsinCik]:
    rows = conn.execute(
        "SELECT isin, cik, ticker, method, status, detail, figi_name FROM isin_cik"
    ).fetchall()
    return {r[0]: IsinCik(*r) for r in rows}


@dataclass(frozen=True)
class IssuerRow:
    issuer_id: str
    lei: str | None
    cik: str | None
    name: str
    country: str | None
    sector_sic: str | None
    sic_description: str | None
    fiscal_year_end: str | None
    state_of_incorporation: str | None
    business_address: str | None
    business_region: str | None
    entity_type: str | None
    filer_category: str | None
    source: str
    source_sha256: str
    retrieved_at: datetime


_ISSUER_COLS = (
    "issuer_id, lei, cik, name, country, sector_sic, sic_description, fiscal_year_end, "
    "state_of_incorporation, business_address, business_region, entity_type, filer_category, "
    "source, source_sha256, retrieved_at"
)


def save_issuer(conn: duckdb.DuckDBPyConnection, row: IssuerRow) -> None:
    values = [getattr(row, c) for c in _ISSUER_COLS.split(", ")]
    values[-1] = _utc_naive(row.retrieved_at)
    conn.execute(
        f"INSERT OR REPLACE INTO issuers ({_ISSUER_COLS}) VALUES ({', '.join('?' * 16)})", values
    )


def load_issuer(conn: duckdb.DuckDBPyConnection, issuer_id: str) -> IssuerRow | None:
    row = conn.execute(
        f"SELECT {_ISSUER_COLS} FROM issuers WHERE issuer_id = ?", [issuer_id]
    ).fetchone()
    if row is None:
        return None
    values = list(row)
    values[-1] = values[-1].replace(tzinfo=UTC)
    return IssuerRow(*values)


def issuer_ids_with_facts(conn: duckdb.DuckDBPyConnection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT DISTINCT issuer_id FROM facts").fetchall()}


@dataclass(frozen=True)
class DocumentRow:
    doc_id: str
    issuer_id: str
    doc_type: str
    period_end: date | None
    published_at: datetime
    retrieved_at: datetime
    source_url: str
    doc_hash: str | None = None


@dataclass(frozen=True)
class FactRow:
    """Ein Abschlusswert, wie er aus der Quelle kommt (SPEC 7.7)."""

    issuer_id: str
    concept: str
    value: Decimal
    unit: str
    unit_raw: str
    currency: str | None
    period_start: date | None
    period_end: date
    fiscal_year: int | None
    fiscal_period: str | None
    form: str | None
    accession: str
    published_at: datetime
    source_type: str
    xbrl_context: str
    raw_sha256: str
    retrieved_at: datetime
    scale: int = 1
    doc_id: str | None = None


@dataclass(frozen=True)
class StoredFact:
    """Ein gespeicherter Abschlusswert, gelesen über `pit_query`."""

    fact_id: int
    issuer_id: str
    concept: str
    value: Decimal
    unit: str
    unit_raw: str
    currency: str | None
    period_start: date | None
    period_end: date
    fiscal_year: int | None
    fiscal_period: str | None
    form: str | None
    accession: str
    published_at: datetime
    xbrl_context: str | None
    raw_sha256: str
    superseded_by: int | None

    @property
    def schluessel(self) -> tuple[str, str, str, date | None, date]:
        return (self.issuer_id, self.concept, self.unit_raw, self.period_start, self.period_end)

    @property
    def quelle(self) -> str:
        """Herkunft für den Rechenweg: XBRL-Konzept, Periode und Einreichung (CLAUDE.md)."""
        start = f"{self.period_start}.." if self.period_start else ""
        return f"{self.concept}@{start}{self.period_end} ({self.form} {self.accession})"


_FACT_COLS = (
    "issuer_id, concept, value, unit, unit_raw, scale, currency, period_start, period_end, "
    "fiscal_year, fiscal_period, form, accession, published_at, source_type, doc_id, "
    "xbrl_context, raw_sha256, retrieved_at"
)
_STORED_COLS = (
    "fact_id, issuer_id, concept, value, unit, unit_raw, currency, period_start, period_end, "
    "fiscal_year, fiscal_period, form, accession, published_at, xbrl_context, raw_sha256, "
    "superseded_by"
)


def _stored(row: tuple[Any, ...]) -> StoredFact:
    values = list(row)
    values[13] = values[13].replace(tzinfo=UTC)
    return StoredFact(*values)


def replace_facts(
    conn: duckdb.DuckDBPyConnection,
    issuer_id: str,
    facts: list[FactRow],
    documents: list[DocumentRow],
) -> int:
    """Ersetzt alle Werte eines Emittenten aus einer neuen Antwort der Quelle.

    Company Facts der SEC sind kumulativ: Jede Antwort enthält alle Fassungen aller
    Einreichungen. Die alte Antwort bleibt in `data/raw/` erhalten (SPEC 7.6). Danach wird
    `superseded_by` für Restatements gesetzt (SPEC 3.2 Nr. 7).
    """
    if any(f.issuer_id != issuer_id for f in facts):
        raise ValueError("Werte gehören zu einem anderen Emittenten")
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "facts.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            for f in facts:
                writer.writerow(
                    [
                        f.issuer_id,
                        f.concept,
                        str(f.value),
                        f.unit,
                        f.unit_raw,
                        f.scale,
                        f.currency,
                        f.period_start,
                        f.period_end,
                        f.fiscal_year,
                        f.fiscal_period,
                        f.form,
                        f.accession,
                        _utc_naive(f.published_at),
                        f.source_type,
                        f.doc_id,
                        f.xbrl_context,
                        f.raw_sha256,
                        _utc_naive(f.retrieved_at),
                    ]
                )
        conn.execute("BEGIN")
        try:
            conn.execute("DELETE FROM facts WHERE issuer_id = ?", [issuer_id])
            types = {
                "issuer_id": "VARCHAR",
                "concept": "VARCHAR",
                "value": "DECIMAL(38, 10)",
                "unit": "VARCHAR",
                "unit_raw": "VARCHAR",
                "scale": "INTEGER",
                "currency": "VARCHAR",
                "period_start": "DATE",
                "period_end": "DATE",
                "fiscal_year": "INTEGER",
                "fiscal_period": "VARCHAR",
                "form": "VARCHAR",
                "accession": "VARCHAR",
                "published_at": "TIMESTAMP",
                "source_type": "VARCHAR",
                "doc_id": "VARCHAR",
                "xbrl_context": "VARCHAR",
                "raw_sha256": "VARCHAR",
                "retrieved_at": "TIMESTAMP",
            }
            if facts:
                conn.execute(
                    f"INSERT INTO facts ({_FACT_COLS}) SELECT * FROM read_csv(?, header = false, "
                    f"columns = {types!r}, nullstr = '', quote = '\"')",
                    [str(csv_path)],
                )
            if documents:
                conn.executemany(
                    "INSERT OR REPLACE INTO documents (doc_id, doc_hash, issuer_id, doc_type, "
                    "period_end, published_at, retrieved_at, source_url) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        [
                            d.doc_id,
                            d.doc_hash,
                            d.issuer_id,
                            d.doc_type,
                            d.period_end,
                            _utc_naive(d.published_at),
                            _utc_naive(d.retrieved_at),
                            d.source_url,
                        ]
                        for d in documents
                    ],
                )
            alle = [
                _stored(r)
                for r in conn.execute(
                    f"SELECT {_STORED_COLS} FROM facts WHERE issuer_id = ?", [issuer_id]
                ).fetchall()
            ]
            updates = [
                [a.neu.fact_id, a.alt.fact_id]  # type: ignore[attr-defined]
                for a in pit.restatements(alle)
            ]
            if updates:
                conn.executemany("UPDATE facts SET superseded_by = ? WHERE fact_id = ?", updates)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return len(facts)


def pit_query(
    conn: duckdb.DuckDBPyConnection,
    *,
    as_of: datetime,
    issuer_id: str,
    concepts: list[str] | None = None,
    fassung: Literal["gueltig", "erste", "einreichung"] = "gueltig",
    accession: str | None = None,
) -> list[StoredFact]:
    """Einziger Lesezugang zu `facts` (HR-07). `as_of` ist Pflicht und braucht eine Zeitzone.

    Werte, die nach `as_of` veröffentlicht wurden, sind unsichtbar.

    - `gueltig`: je Wert die zum Zeitpunkt `as_of` maßgebliche Fassung. Restatements gelten erst
      ab ihrem Veröffentlichungstag, bloße Rundungen ersetzen keinen genauen Wert (core/pit.py).
    - `erste`: je Wert die erste Veröffentlichung, wie damals gemeldet.
    - `einreichung`: alle Werte genau einer Einreichung (`accession`), etwa eines 10-K.
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of ohne Zeitzone")
    sql = f"SELECT {_STORED_COLS} FROM facts WHERE issuer_id = ? AND published_at <= ?"
    params: list[Any] = [issuer_id, _utc_naive(as_of)]
    if concepts is not None:
        if not concepts:
            return []
        sql += f" AND concept IN ({', '.join('?' * len(concepts))})"
        params += concepts
    if fassung == "einreichung":
        if accession is None:
            raise ValueError("fassung='einreichung' braucht accession")
        sql += " AND accession = ?"
        params.append(accession)
    rows = [_stored(r) for r in conn.execute(sql, params).fetchall()]
    if fassung == "gueltig":
        rows = pit.gueltig(rows, as_of)
    elif fassung == "erste":
        rows = pit.erste(rows, as_of)
    return sorted(rows, key=lambda f: (f.concept, f.period_end, f.period_start or f.period_end))


@dataclass(frozen=True)
class DqFlag:
    issuer_id: str
    check_id: str
    severity: str
    period_end: date | None
    concept: str | None
    detail: str
    trace_json: str | None = None


def replace_dq_flags(
    conn: duckdb.DuckDBPyConnection, issuer_id: str, flags: list[DqFlag], now: datetime
) -> None:
    conn.execute("BEGIN")
    try:
        conn.execute("DELETE FROM dq_flags WHERE issuer_id = ?", [issuer_id])
        if flags:
            conn.executemany(
                "INSERT INTO dq_flags VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    [
                        f.issuer_id,
                        f.check_id,
                        f.severity,
                        f.period_end,
                        f.concept,
                        f.detail,
                        f.trace_json,
                        _utc_naive(now),
                    ]
                    for f in flags
                ],
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def load_dq_flags(conn: duckdb.DuckDBPyConnection, issuer_id: str) -> list[DqFlag]:
    rows = conn.execute(
        "SELECT issuer_id, check_id, severity, period_end, concept, detail, trace_json "
        "FROM dq_flags WHERE issuer_id = ? ORDER BY check_id, period_end, concept",
        [issuer_id],
    ).fetchall()
    return [DqFlag(*r) for r in rows]


def us_listings(
    conn: duckdb.DuckDBPyConnection, extra: Iterable[str] = ()
) -> list[tuple[str, str, str | None]]:
    """ISIN, Börsenname und LEI-Name aller gelisteten Titel mit US-ISIN und der ISINs in `extra`
    (etwa Lucas Zuordnungen für Stammaktien ausländischer SEC-Melder)."""
    extra = list(extra)
    sql = (
        "SELECT isin, name, CASE WHEN lei_plausible THEN lei_name END FROM listings "
        "WHERE listed AND (isin_country = 'US'"
    )
    if extra:
        sql += f" OR isin IN ({', '.join('?' * len(extra))})"
    rows = conn.execute(sql + ") ORDER BY isin", extra).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def listing_lei(conn: duckdb.DuckDBPyConnection, isins: list[str]) -> str | None:
    """Plausible LEI, wenn alle genannten ISINs dieselbe haben."""
    if not isins:
        return None
    rows = conn.execute(
        f"SELECT DISTINCT lei FROM listings WHERE lei_plausible AND isin IN "
        f"({', '.join('?' * len(isins))})",
        isins,
    ).fetchall()
    leis = {r[0] for r in rows if r[0]}
    return leis.pop() if len(leis) == 1 else None


def restatements(
    conn: duckdb.DuckDBPyConnection, *, as_of: datetime, issuer_id: str
) -> list[tuple[StoredFact, StoredFact]]:
    """Paare (alte Fassung, geänderte Fassung), deren Änderung bis `as_of` bekannt war."""
    if as_of.tzinfo is None:
        raise ValueError("as_of ohne Zeitzone")
    cols = ", ".join(f"{p}.{c}" for p in ("a", "b") for c in _STORED_COLS.split(", "))
    rows = conn.execute(
        f"SELECT {cols} FROM facts a JOIN facts b ON a.superseded_by = b.fact_id "
        "WHERE a.issuer_id = ? AND b.published_at <= ? ORDER BY a.concept, a.period_end",
        [issuer_id, _utc_naive(as_of)],
    ).fetchall()
    n = len(_STORED_COLS.split(", "))
    return [(_stored(r[:n]), _stored(r[n:])) for r in rows]


# ------------------------------------------------------------------ Kennzahlen (Bauschritt 3)


@dataclass(frozen=True)
class MetricRow:
    issuer_id: str
    metric_id: str
    metric_version: str
    statistik: str
    period_end: date
    value: Decimal | None
    grund: str | None
    ungereimtheit: str | None
    warnungen: tuple[str, ...]
    vermerke: tuple[str, ...]
    calc_trace_json: str | None


@dataclass(frozen=True)
class HinweisRow:
    issuer_id: str
    regel: str
    an_agent: str
    abteilung: str
    anlass: str
    metric_id: str | None
    period_end: date | None
    detail: str
    status: str


def replace_metrics(
    conn: duckdb.DuckDBPyConnection,
    *,
    issuer_id: str,
    as_of: datetime,
    stichtag: date | None,
    methodology_version: str,
    werte: list[Kennzahlwert],
    hinweise: list[Hinweis],
    now: datetime,
) -> str:
    """Ersetzt Kennzahlen und offene Hinweise einer Firma. Gespeichert wird nur der letzte Lauf,
    die Laufliste `metric_runs` bleibt erhalten. Rechenwege nur für die Jahreswerte des
    Stichtags."""
    run_id = f"metrics:{issuer_id}:{_utc_naive(as_of).isoformat()}"
    jetzt = _utc_naive(now)
    conn.execute("BEGIN")
    try:
        conn.execute("DELETE FROM metrics WHERE issuer_id = ?", [issuer_id])
        conn.execute("DELETE FROM hinweise WHERE issuer_id = ? AND status = 'offen'", [issuer_id])
        conn.execute("DELETE FROM metric_runs WHERE run_id = ?", [run_id])
        conn.execute(
            "INSERT INTO metric_runs VALUES (?, ?, ?, ?, ?, ?)",
            [run_id, issuer_id, _utc_naive(as_of), stichtag, methodology_version, jetzt],
        )
        if werte:
            conn.executemany(
                "INSERT INTO metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    [
                        run_id,
                        issuer_id,
                        w.metric_id,
                        w.metric_version,
                        w.statistik,
                        w.period_end,
                        None if w.ergebnis.wert is None else str(w.ergebnis.wert),
                        w.ergebnis.grund,
                        w.ergebnis.ungereimtheit,
                        json.dumps(list(w.ergebnis.warnungen), ensure_ascii=False),
                        json.dumps(list(w.ergebnis.vermerke), ensure_ascii=False),
                        w.ergebnis.rechenweg_json()
                        if w.period_end == stichtag and w.statistik == "wert"
                        else None,
                        jetzt,
                    ]
                    for w in werte
                ],
            )
        if hinweise:
            conn.executemany(
                "INSERT INTO hinweise VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'offen', ?)",
                [
                    [
                        run_id,
                        issuer_id,
                        h.regel,
                        h.an,
                        h.abteilung,
                        h.anlass,
                        h.metric_id,
                        h.period_end,
                        h.detail,
                        jetzt,
                    ]
                    for h in hinweise
                ],
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return run_id


def load_metrics(
    conn: duckdb.DuckDBPyConnection,
    issuer_id: str,
    metric_id: str | None = None,
    statistik: str | None = None,
) -> list[MetricRow]:
    sql = (
        "SELECT issuer_id, metric_id, metric_version, statistik, period_end, value, grund, "
        "ungereimtheit, warnungen_json, vermerke_json, calc_trace_json FROM metrics "
        "WHERE issuer_id = ?"
    )
    params: list[Any] = [issuer_id]
    if metric_id:
        sql += " AND metric_id = ?"
        params.append(metric_id)
    if statistik:
        sql += " AND statistik = ?"
        params.append(statistik)
    rows = conn.execute(sql + " ORDER BY metric_id, statistik, period_end DESC", params).fetchall()
    return [
        MetricRow(
            r[0],
            r[1],
            r[2],
            r[3],
            r[4],
            None if r[5] is None else Decimal(r[5]),
            r[6],
            r[7],
            tuple(json.loads(r[8])),
            tuple(json.loads(r[9])),
            r[10],
        )
        for r in rows
    ]


def load_metric_run(
    conn: duckdb.DuckDBPyConnection, issuer_id: str
) -> tuple[str, datetime, date | None, str] | None:
    """Letzter Lauf: run_id, as_of, Stichtag, Methodikversion."""
    row = conn.execute(
        "SELECT run_id, as_of, stichtag, methodology_version FROM metric_runs "
        "WHERE issuer_id = ? ORDER BY computed_at DESC LIMIT 1",
        [issuer_id],
    ).fetchone()
    return None if row is None else (row[0], row[1], row[2], row[3])


def load_hinweise(
    conn: duckdb.DuckDBPyConnection, issuer_id: str | None = None, status: str = "offen"
) -> list[HinweisRow]:
    sql = (
        "SELECT issuer_id, regel, an_agent, abteilung, anlass, metric_id, period_end, detail, "
        "status FROM hinweise WHERE status = ?"
    )
    params: list[Any] = [status]
    if issuer_id:
        sql += " AND issuer_id = ?"
        params.append(issuer_id)
    rows = conn.execute(sql + " ORDER BY issuer_id, regel, metric_id, period_end", params)
    return [HinweisRow(*r) for r in rows.fetchall()]


# ------------------------------------------------------------------ Kurse (Bauschritt 4)


@dataclass(frozen=True)
class PriceSymbol:
    isin: str
    symbol: str | None
    exch_code: str | None
    method: str
    status: str
    detail: str
    quelle_name: str | None
    waehrung: str | None
    boerse: str | None
    warnungen: tuple[str, ...]
    checked_at: datetime
    retrieved_at: datetime | None


@dataclass(frozen=True)
class PriceRow:
    isin: str
    date: date
    close: Decimal
    adj_close: Decimal | None
    volume: int | None
    currency: str | None
    symbol: str
    source: str


@dataclass(frozen=True)
class PriceEvent:
    isin: str
    date: date
    kind: str
    value: Decimal | None
    numerator: Decimal | None
    denominator: Decimal | None
    currency: str | None
    symbol: str
    source: str


def save_price_symbol(conn: duckdb.DuckDBPyConnection, p: PriceSymbol) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO price_symbols VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            p.isin,
            p.symbol,
            p.exch_code,
            p.method,
            p.status,
            p.detail,
            p.quelle_name,
            p.waehrung,
            p.boerse,
            json.dumps(list(p.warnungen), ensure_ascii=False),
            _utc_naive(p.checked_at),
            _utc_naive(p.retrieved_at) if p.retrieved_at else None,
        ],
    )


def load_price_symbol(conn: duckdb.DuckDBPyConnection, isin: str) -> PriceSymbol | None:
    row = conn.execute("SELECT * FROM price_symbols WHERE isin = ?", [isin]).fetchone()
    if row is None:
        return None
    return PriceSymbol(
        row[0],
        row[1],
        row[2],
        row[3],
        row[4],
        row[5],
        row[6],
        row[7],
        row[8],
        tuple(json.loads(row[9])),
        row[10].replace(tzinfo=UTC),
        row[11].replace(tzinfo=UTC) if row[11] else None,
    )


def save_prices(
    conn: duckdb.DuckDBPyConnection,
    rows: list[PriceRow],
    events: list[PriceEvent],
    raw_sha256: str,
    retrieved_at: datetime,
) -> None:
    """Neuere Abrufe überschreiben ältere je Tag und Quelle (Yahoo korrigiert gelegentlich)."""
    conn.execute("BEGIN")
    try:
        if rows:
            conn.executemany(
                "INSERT OR REPLACE INTO prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    [
                        r.isin,
                        r.date,
                        str(r.close),
                        None if r.adj_close is None else str(r.adj_close),
                        r.volume,
                        r.currency,
                        r.symbol,
                        r.source,
                        raw_sha256,
                        _utc_naive(retrieved_at),
                    ]
                    for r in rows
                ],
            )
        if events:
            conn.executemany(
                "INSERT OR REPLACE INTO price_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    [
                        e.isin,
                        e.date,
                        e.kind,
                        None if e.value is None else str(e.value),
                        None if e.numerator is None else str(e.numerator),
                        None if e.denominator is None else str(e.denominator),
                        e.currency,
                        e.symbol,
                        e.source,
                        raw_sha256,
                    ]
                    for e in events
                ],
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def delete_prices_from(conn: duckdb.DuckDBPyConnection, isin: str, ab: date, source: str) -> None:
    """Entfernt laufende Kurse ab einem Tag (gespeichert vor dem Handelsschluss)."""
    conn.execute(
        "DELETE FROM prices WHERE isin = ? AND date >= ? AND source = ?", [isin, ab, source]
    )


def _dec(v: str | None) -> Decimal | None:
    return None if v is None else Decimal(v)


def load_prices(
    conn: duckdb.DuckDBPyConnection, isin: str, bis: date | None = None
) -> list[PriceRow]:
    """Kurse eines Titels, ältester zuerst. `bis` begrenzt auf Handelstage bis einschließlich."""
    sql = (
        "SELECT isin, date, close, adj_close, volume, currency, symbol, source FROM prices "
        "WHERE isin = ?"
    )
    params: list[Any] = [isin]
    if bis is not None:
        sql += " AND date <= ?"
        params.append(bis)
    rows = conn.execute(sql + " ORDER BY date", params).fetchall()
    return [PriceRow(r[0], r[1], Decimal(r[2]), _dec(r[3]), r[4], r[5], r[6], r[7]) for r in rows]


def load_price_events(conn: duckdb.DuckDBPyConnection, isin: str) -> list[PriceEvent]:
    rows = conn.execute(
        "SELECT isin, date, kind, value, numerator, denominator, currency, symbol, source "
        "FROM price_events WHERE isin = ? ORDER BY date, kind",
        [isin],
    ).fetchall()
    return [
        PriceEvent(r[0], r[1], r[2], _dec(r[3]), _dec(r[4]), _dec(r[5]), r[6], r[7], r[8])
        for r in rows
    ]


def listing_info(conn: duckdb.DuckDBPyConnection, isin: str) -> tuple[str, str] | None:
    """Börsenname und Land (Hauptsitz) eines gelisteten Titels."""
    row = conn.execute("SELECT name, country FROM listings WHERE isin = ?", [isin]).fetchone()
    return None if row is None else (row[0], row[1])
