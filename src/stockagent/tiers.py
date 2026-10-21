"""Indexstufe Tier 1 bis 4 (SPEC 7.9, ADR 0004).

Die Stufe ist ein Filter, kein Qualitätsurteil, und geht nicht in die Note ein (HR-13). Höchste
zutreffende Stufe zählt, bezogen auf den Heimatmarkt: ein Index mit Land zählt nur für Titel aus
diesem Land, länderübergreifende Indizes für alle.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from stockagent.core.identifiers import isin_is_valid
from stockagent.data import rawstore, store
from stockagent.paths import Paths


def konfig(paths: Paths) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((paths.config / "tiers.yaml").read_text("utf-8"))
    return data


def stufe(land: str | None, indizes: list[str], cfg: dict[str, Any]) -> tuple[int, list[str]]:
    """(Stufe, zählende Indizes). Ohne zutreffenden Index Stufe 4."""
    zaehlend = [
        i for i in indizes if i in cfg["indizes"] and cfg["indizes"][i]["land"] in ("global", land)
    ]
    if not zaehlend:
        return 4, []
    beste = min(int(cfg["indizes"][i]["stufe"]) for i in zaehlend)
    return beste, sorted(i for i in zaehlend if int(cfg["indizes"][i]["stufe"]) == beste)


def isins_aus_datei(raw: bytes) -> list[str]:
    """ISINs aus einer Bestandsliste (CSV mit Komma oder Semikolon, Spalte „ISIN“). Kopfzeilen
    vor der Tabelle, wie bei ETF-Anbietern üblich, werden übersprungen. Nur gültige ISINs."""
    text = raw.decode("utf-8-sig", errors="replace")
    zeilen = text.splitlines()
    kopf = next(
        (
            i
            for i, z in enumerate(zeilen)
            if "ISIN" in z.upper().split(",") or "ISIN" in z.upper().split(";")
        ),
        None,
    )
    if kopf is None:
        raise ValueError("Datei ohne Spalte ISIN")
    trenner = ";" if zeilen[kopf].count(";") > zeilen[kopf].count(",") else ","
    leser = csv.DictReader(io.StringIO("\n".join(zeilen[kopf:])), delimiter=trenner)
    spalte = next(k for k in (leser.fieldnames or []) if k.strip().upper() == "ISIN")
    out = []
    for z in leser:
        isin = (z.get(spalte) or "").strip().upper()
        if isin_is_valid(isin):
            out.append(isin)
    return sorted(set(out))


@dataclass
class ImportErgebnis:
    index_id: str
    mitglieder: int
    neu: int
    raus: int


def importieren(paths: Paths, index_id: str, datei: Path, stand: date) -> ImportErgebnis:
    cfg = konfig(paths)
    if index_id not in cfg["indizes"]:
        raise ValueError(f"Index {index_id} fehlt in config/tiers.yaml")
    raw = datei.read_bytes()
    isins = isins_aus_datei(raw)
    if not isins:
        raise ValueError("keine gültige ISIN in der Datei")
    ref = rawstore.save(paths.raw, raw, f"datei:{datei.name}", datetime.now(UTC))
    conn = store.connect(paths.db)
    try:
        neu, raus = store.replace_index_members(
            conn, index_id, isins, stand, f"Import {datei.name}", ref.sha256
        )
    finally:
        conn.close()
    return ImportErgebnis(index_id, len(isins), neu, raus)


def stufen_aller(paths: Paths) -> dict[str, tuple[int, list[str]]]:
    """Stufe je ISIN des Universums."""
    cfg = konfig(paths)
    conn = store.connect(paths.db)
    try:
        mitglied = store.index_memberships(conn)
        laender = dict(conn.execute("SELECT isin, country FROM listings").fetchall())
    finally:
        conn.close()
    return {isin: stufe(land, mitglied.get(isin, []), cfg) for isin, land in laender.items()}
