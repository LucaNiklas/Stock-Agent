"""Universum aktualisieren (SPEC 7.1, Bauschritt 1).

Ablauf: Downloadseiten lesen, Dateien laden, roh ablegen, einlesen, ISIN prüfen, LEI ergänzen,
Abweichung zur letzten Liste prüfen, in DuckDB schreiben.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import yaml

from stockagent.core.identifiers import change_exceeds, isin_is_valid
from stockagent.data import rawstore, store
from stockagent.data.http import fetch
from stockagent.data.sources import deutsche_boerse, gleif
from stockagent.paths import Paths

Fetcher = Callable[[str, str], bytes]


@dataclass
class UpdateResult:
    applied: bool
    stock_count: int
    previous_count: int | None
    source_as_of: date | None = None
    with_lei: int = 0
    invalid_isins: list[str] = field(default_factory=list)
    message: str = ""


def load_config(paths: Paths) -> dict[str, Any]:
    cfg: dict[str, Any] = yaml.safe_load((paths.config / "sources.yaml").read_text("utf-8"))
    return cfg


def _download(fetcher: Fetcher, ua: str, page_url: str, file_name: str) -> tuple[str, bytes]:
    page = fetcher(page_url, ua).decode("utf-8", errors="replace")
    url = deutsche_boerse.find_file_url(page, file_name, page_url)
    return url, fetcher(url, ua)


def update(
    paths: Paths,
    *,
    force: bool = False,
    refresh: bool = False,
    fetcher: Fetcher = fetch,
    now: datetime | None = None,
) -> UpdateResult:
    now = now or datetime.now(UTC)
    cfg = load_config(paths)
    ua: str = cfg["user_agent"]
    db_cfg, ucfg = cfg["deutsche_boerse"], cfg["universe"]
    conn = store.connect(paths.db)
    try:
        previous = store.last_stock_count(conn)
        last = store.last_retrieved_at(conn)
        if (
            not refresh
            and last is not None
            and now - last < timedelta(days=ucfg["min_refresh_days"])
        ):
            return UpdateResult(
                False,
                previous or 0,
                previous,
                message=f"Liste vom {last:%d.%m.%Y} ist aktuell genug "
                "(--refresh lädt trotzdem neu).",
            )

        fra_url, fra_raw = _download(
            fetcher, ua, db_cfg["frankfurt_page"], db_cfg["frankfurt_file"]
        )
        xet_url, xet_raw = _download(fetcher, ua, db_cfg["xetra_page"], db_cfg["xetra_file"])
        fra_ref = rawstore.save(paths.raw, fra_raw, fra_url, now)
        xet_ref = rawstore.save(paths.raw, xet_raw, xet_url, now)
        frankfurt = deutsche_boerse.parse(fra_raw)
        xetra = deutsche_boerse.parse(xet_raw)

        by_isin = {i.isin: i for i in frankfurt.instruments}
        for inst in xetra.instruments:  # Xetra-Titel ohne Frankfurt-Notiz ebenfalls aufnehmen
            by_isin.setdefault(inst.isin, inst)
        on_xetra = {i.isin for i in xetra.instruments}

        gleif_url = cfg["gleif"]["isin_lei_url"]
        gleif_raw = fetcher(gleif_url, ua)
        gleif_ref = rawstore.save(paths.raw, gleif_raw, gleif_url, now)
        leis = gleif.lei_by_isin(gleif_raw, by_isin)

        rows = [
            store.ListingRow(
                isin=i.isin,
                name=i.name,
                wkn=i.wkn,
                mnemonic=i.mnemonic,
                isin_country=i.isin_country,
                currency=i.currency,
                primary_mic=i.primary_mic,
                on_xetra=i.isin in on_xetra,
                lei=leis.get(i.isin),
                isin_valid=isin_is_valid(i.isin),
            )
            for i in sorted(by_isin.values(), key=lambda x: x.isin)
        ]
        result = UpdateResult(
            applied=False,
            stock_count=len(rows),
            previous_count=previous,
            source_as_of=frankfurt.as_of,
            with_lei=len(leis),
            invalid_isins=[r.isin for r in rows if not r.isin_valid],
        )
        too_big = previous is not None and change_exceeds(
            previous, len(rows), ucfg["max_change_pct"]
        )
        if too_big and not force:
            result.message = (
                f"Anzahl ändert sich von {previous} auf {len(rows)}, mehr als "
                f"{ucfg['max_change_pct']} Prozent. Nicht übernommen. Quelle prüfen, "
                "dann mit --force übernehmen."
            )
            return result
        store.apply_snapshot(
            conn,
            rows,
            retrieved_at=now,
            source_as_of=frankfurt.as_of,
            frankfurt_sha=fra_ref.sha256,
            xetra_sha=xet_ref.sha256,
            gleif_sha=gleif_ref.sha256,
            forced=force,
        )
        result.applied = True
        result.message = "Liste übernommen."
        return result
    finally:
        conn.close()
