"""Anzeige des Universums im Terminal und als durchsuchbare HTML-Seite (Bauschritt 1)."""

from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass
from datetime import date
from importlib.resources import files

import duckdb

from stockagent.tr_checks import TrCheck, TrStatus

TR_LABEL = {
    TrStatus.UNGEPRUEFT: "nicht geprüft",
    TrStatus.BESTAETIGT: "handelbar (geprüft)",
    TrStatus.NICHT_HANDELBAR: "nicht handelbar (geprüft)",
}


@dataclass(frozen=True)
class ViewRow:
    name: str
    isin: str
    wkn: str
    land: str
    heimatboerse: str
    xetra: bool
    lei: str
    tr_status: str


@dataclass(frozen=True)
class ViewMeta:
    stock_count: int
    source_as_of: date | None
    retrieved_at: str
    tr_checked: int


def query(
    conn: duckdb.DuckDBPyConnection,
    checks: dict[str, TrCheck],
    *,
    search: str | None = None,
    country: str | None = None,
    tr_only: bool = False,
    include_delisted: bool = False,
) -> list[ViewRow]:
    sql = "SELECT name, isin, wkn, isin_country, primary_mic, on_xetra, lei FROM listings WHERE 1=1"
    params: list[object] = []
    if not include_delisted:
        sql += " AND listed"
    if search:
        sql += " AND (name ILIKE ? OR isin = upper(?) OR wkn = upper(?) OR mnemonic = upper(?))"
        params += [f"%{search}%", search, search, search]
    if country:
        sql += " AND isin_country = upper(?)"
        params.append(country)
    sql += " ORDER BY name"
    rows = []
    for name, isin, wkn, land, mic, xetra, lei in conn.execute(sql, params).fetchall():
        check = checks.get(isin)
        status = check.status if check else TrStatus.UNGEPRUEFT
        if tr_only and status is not TrStatus.BESTAETIGT:
            continue
        rows.append(
            ViewRow(
                name,
                isin,
                wkn or "",
                land or "",
                mic or "",
                bool(xetra),
                lei or "",
                TR_LABEL[status],
            )
        )
    return rows


def meta(conn: duckdb.DuckDBPyConnection, checks: dict[str, TrCheck]) -> ViewMeta | None:
    row = conn.execute(
        "SELECT stock_count, source_as_of, retrieved_at FROM universe_snapshots "
        "ORDER BY snapshot_id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return ViewMeta(int(row[0]), row[1], f"{row[2]:%d.%m.%Y %H:%M} UTC", len(checks))


_PAGE = (files("stockagent.report") / "templates" / "universe.html").read_text("utf-8")


def to_html(rows: list[ViewRow], info: ViewMeta) -> str:
    stand = info.source_as_of.strftime("%d.%m.%Y") if info.source_as_of else "unbekannt"
    count = f"{info.stock_count:,}".replace(",", ".")
    meta_text = (
        f"{count} Aktien aus den Instrumentenlisten von Börse Frankfurt und Xetra "
        f"(Deutsche Börse, Stand {stand}, abgerufen {info.retrieved_at}). "
        f"Handelbarkeit bei Trade Republic von Luca geprüft: {info.tr_checked}. "
        "Recherche-Grundlage, keine Anlageberatung."
    )
    data = json.dumps([asdict(r) for r in rows], ensure_ascii=False).replace("</", "<\\/")
    return _PAGE.replace("__META__", html.escape(meta_text)).replace("__DATA__", data)
