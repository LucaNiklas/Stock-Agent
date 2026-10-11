"""Universum aktualisieren (SPEC 7.1, Bauschritt 1).

Ablauf: Downloadseiten lesen, Dateien laden, roh ablegen, einlesen, ISIN prüfen, LEI zuordnen,
Stammdaten der LEI laden (Name, Sitz, Hauptsitz), Namen auf Plausibilität prüfen, Land wählen,
Abweichung zur letzten Liste prüfen, in DuckDB schreiben, alte GLEIF-Rohdaten aufräumen.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import yaml

from stockagent.core.identifiers import (
    change_exceeds,
    choose_country,
    is_depositary_receipt,
    isin_is_valid,
    names_plausibly_match,
)
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
    lei_implausible: int = 0
    country_from_gleif: int = 0
    country_conflicts: int = 0
    pruned_raw: int = 0
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
    sleep: Callable[[float], None] = time.sleep,
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

        gcfg = cfg["gleif"]
        gleif_url = gcfg["isin_lei_url"]
        gleif_raw = fetcher(gleif_url, ua)
        gleif_ref = rawstore.save(paths.raw, gleif_raw, gleif_url, now)
        leis = gleif.lei_by_isin(gleif_raw, by_isin)
        raw_used = [
            store.RawUse("frankfurt", fra_ref.sha256, fra_url),
            store.RawUse("xetra", xet_ref.sha256, xet_url),
            store.RawUse("gleif_mapping", gleif_ref.sha256, gleif_url),
        ]

        entities: dict[str, gleif.Entity] = {}
        for n, url in enumerate(
            gleif.entity_urls(gcfg["api_url"], leis.values(), gcfg["batch_size"])
        ):
            if n:
                sleep(gcfg["api_pause_s"])
            content = fetcher(url, ua)
            ref = rawstore.save(paths.raw, content, url, now)
            raw_used.append(store.RawUse("gleif_entities", ref.sha256, url))
            entities.update(gleif.parse_entities(content))

        rows = []
        for i in sorted(by_isin.values(), key=lambda x: x.isin):
            lei = leis.get(i.isin)
            ent = entities.get(lei) if lei else None
            plausible = (
                any(names_plausibly_match(i.name, n) for n in ent.all_names) if ent else None
            )
            receipt = is_depositary_receipt(i.name)
            country, source = choose_country(
                i.isin_country,
                ent.seat_country if ent else None,
                ent.hq_country if ent else None,
                bool(plausible),
                receipt,
            )
            rows.append(
                store.ListingRow(
                    isin=i.isin,
                    name=i.name,
                    wkn=i.wkn,
                    mnemonic=i.mnemonic,
                    isin_country=i.isin_country,
                    currency=i.currency,
                    primary_mic=i.primary_mic,
                    on_xetra=i.isin in on_xetra,
                    lei=lei,
                    lei_name=ent.legal_name if ent else None,
                    lei_status=ent.status if ent else None,
                    lei_plausible=plausible,
                    legal_country=ent.seat_country if ent else None,
                    hq_country=ent.hq_country if ent else None,
                    country=country,
                    country_source=source,
                    is_receipt=receipt,
                    isin_valid=isin_is_valid(i.isin),
                )
            )
        result = UpdateResult(
            applied=False,
            stock_count=len(rows),
            previous_count=previous,
            source_as_of=frankfurt.as_of,
            with_lei=len(leis),
            lei_implausible=sum(1 for r in rows if r.lei_plausible is False),
            country_from_gleif=sum(1 for r in rows if r.country_source == "gleif"),
            country_conflicts=sum(1 for r in rows if r.country_source == "konflikt"),
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
            raw=raw_used,
            forced=force,
        )
        keep = store.raw_in_recent_snapshots(
            conn, ("gleif_mapping", "gleif_entities"), gcfg["keep_snapshots"]
        )
        result.pruned_raw = len(
            rawstore.prune(paths.raw, (gcfg["isin_lei_url"], gcfg["api_url"]), keep)
        )
        result.applied = True
        result.message = "Liste übernommen."
        return result
    finally:
        conn.close()
