"""Ablauf Abschlussdaten EU aus ESEF (Bauschritt 7, SPEC 7.2, ADR 0009).

Je angefragter ISIN: LEI aus dem Universum (GLEIF), Einreichungen bei filings.xbrl.org, die
letzten `jahre` Jahresberichte als xBRL-JSON laden, Werte als `facts` unter `lei:<LEI>` speichern
(Restatements wie bei der SEC über `superseded_by`), Datenqualität DQ-01 bis DQ-08 ohne zweiten
Weg (der Bericht selbst ist die einzige Quelle). Rohdateien mit SHA-256 in `data/raw/`.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import yaml

from stockagent.data import concepts, quality, store
from stockagent.data.http import FetchError, fetch
from stockagent.data.sources import esef
from stockagent.paths import Paths

Progress = Callable[[str], None]


def _noop(_: str) -> None:
    pass


@dataclass
class EsefErgebnis:
    isin: str
    issuer_id: str | None = None
    einreichungen: int = 0
    werte: int = 0
    fehler: str | None = None
    flags: Counter[str] = field(default_factory=Counter)


def _titel(conn: object, isin: str) -> tuple[str | None, str, str | None]:
    row = conn.execute(  # type: ignore[attr-defined]
        "SELECT lei, name, country FROM listings WHERE isin = ?", [isin]
    ).fetchone()
    return (row[0], row[1], row[2]) if row else (None, isin, None)


def _sic_ueber_lei(conn: object, lei: str) -> tuple[str | None, str | None]:
    """SIC eines SEC-Melders mit derselben LEI (etwa über ein ADR). Sonst keine Branche."""
    row = conn.execute(  # type: ignore[attr-defined]
        "SELECT sector_sic, sic_description FROM issuers WHERE lei = ? AND issuer_id LIKE 'sec:%' "
        "AND sector_sic IS NOT NULL LIMIT 1",
        [lei],
    ).fetchone()
    return (row[0], row[1]) if row else (None, None)


def update(
    paths: Paths,
    isins: list[str],
    *,
    fetcher: Callable[..., bytes] = fetch,
    sleep: Callable[[float], None] = time.sleep,
    now: datetime | None = None,
    progress: Progress = _noop,
) -> list[EsefErgebnis]:
    now = now or datetime.now(UTC)
    cfg = yaml.safe_load((paths.config / "sources.yaml").read_text("utf-8"))
    ecfg = cfg["esef"]
    client = esef.EsefClient(
        ecfg, cfg["user_agent"], paths.raw, fetcher=fetcher, sleep=sleep, now=lambda: now
    )
    cmap = concepts.load(paths.config)
    qcfg = yaml.safe_load((paths.config / "quality.yaml").read_text("utf-8"))
    out = []
    conn = store.connect(paths.db)
    try:
        for isin in dict.fromkeys(i.upper() for i in isins):
            erg = EsefErgebnis(isin)
            out.append(erg)
            lei, name, land = _titel(conn, isin)
            if not lei:
                erg.fehler = "keine LEI im Universum (GLEIF)"
                continue
            progress(f"ESEF: {isin} ({name})")
            try:
                liste = client.einreichungen(lei)
            except (FetchError, esef.EsefFormatError) as exc:
                erg.fehler = str(exc)
                continue
            gut = [e for e in liste if e.fehler <= int(ecfg["max_fehler"])]
            if not gut:
                erg.fehler = "keine ESEF-Einreichung bei filings.xbrl.org" + (
                    " (deutsche Berichte fehlen dort)" if land == "DE" else ""
                )
                continue
            # Je Geschäftsjahr die zuletzt aufgenommene Fassung, die letzten `jahre` Jahre
            je_jahr = {e.period_end: e for e in gut}
            auswahl = sorted(je_jahr.values(), key=lambda e: e.period_end)[-int(ecfg["jahre"]) :]
            facts: list[store.FactRow] = []
            docs: list[store.DocumentRow] = []
            uebersprungen: Counter[str] = Counter()
            for e in auswahl:
                url = client.url(e.json_url)
                try:
                    raw, ref = client.get(url)
                    f, d, skip = esef.parse_xbrl_json(
                        raw, e, raw_sha256=ref.sha256, retrieved_at=ref.retrieved_at, source_url=url
                    )
                except (FetchError, esef.EsefFormatError) as exc:
                    erg.fehler = f"{e.fxo_id}: {exc}"
                    continue
                facts.extend(f)
                docs.append(d)
                uebersprungen.update(skip)
            if not facts:
                erg.fehler = erg.fehler or "keine Werte in den Einreichungen"
                continue
            iid = esef.issuer_id(lei)
            sic, sic_text = _sic_ueber_lei(conn, lei)
            letzte = auswahl[-1]
            store.save_issuer(
                conn,
                store.IssuerRow(
                    issuer_id=iid,
                    lei=lei,
                    cik=None,
                    name=name,
                    country=land,
                    sector_sic=sic,
                    sic_description=sic_text,
                    fiscal_year_end=f"{letzte.period_end:%m%d}",
                    state_of_incorporation=None,
                    business_address=None,
                    business_region=None,
                    entity_type=None,
                    filer_category=None,
                    source="filings.xbrl.org",
                    source_sha256=letzte.fxo_id,
                    retrieved_at=now,
                ),
            )
            erg.issuer_id, erg.einreichungen = iid, len(docs)
            erg.werte = store.replace_facts(conn, iid, facts, docs)
            ctx = quality.Kontext(
                issuer_id=iid,
                as_of=now,
                facts=store.pit_query(conn, as_of=now, issuer_id=iid),
                restatements=store.restatements(conn, as_of=now, issuer_id=iid),
                fiscal_year_end=f"{letzte.period_end:%m%d}",
                skipped_units=Counter(
                    {k: v for k, v in uebersprungen.items() if k.startswith("Einheit")}
                ),
            )
            flags = quality.run(ctx, cmap, qcfg)
            store.replace_dq_flags(conn, iid, flags, now)
            erg.flags = Counter(f.severity for f in flags)
    finally:
        conn.close()
    return out
