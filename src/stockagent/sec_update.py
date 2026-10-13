"""Abschlussdaten USA laden (Bauschritt 2, Abteilung Recherche, SPEC 8.1).

Ablauf nach der Quellenkarte (`config/source_map.yaml`):

1. Zuordnung ISIN -> CIK für alle US-ISINs des Universums (ADR 0002): OpenFIGI liefert den
   US-Ticker, die Tickerliste der SEC die CIK, ein Namensabgleich prüft die Plausibilität.
   Lucas Einträge in `state/cik_overrides.yaml` haben Vorrang. Unsicheres bleibt leer.
2. Stammdaten je CIK aus den Submissions: SIC, Geschäftsadresse, Gründungsstaat,
   Geschäftsjahresende.
3. Nur für die Auswahl (`--isin`, `--limit`): Company Facts, XBRL des letzten Jahresberichts,
   Datenqualitätsprüfungen (SPEC 3.2).
"""

from __future__ import annotations

import dataclasses
import re
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from stockagent.core.identifiers import name_tokens, names_plausibly_match
from stockagent.data import concepts, quality, store
from stockagent.data.http import FetchError, fetch
from stockagent.data.sources import openfigi, sec, sec_xbrl
from stockagent.paths import Paths

Progress = Callable[[str], None]


def _noop(_: str) -> None:
    pass


# ------------------------------------------------------------------ Lucas Zuordnungen


def overrides_path(paths: Paths) -> Path:
    return paths.root / "state" / "cik_overrides.yaml"


def load_overrides(path: Path) -> dict[str, str | None]:
    """ISIN -> CIK (10 Ziffern) oder None für "kein SEC-Melder"."""
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text("utf-8")) or {}
    return {isin: (sec.cik10(v["cik"]) if v.get("cik") else None) for isin, v in data.items()}


def record_override(path: Path, isin: str, cik: str | None, on: date) -> None:
    data: dict[str, Any] = {}
    if path.exists():
        data = yaml.safe_load(path.read_text("utf-8")) or {}
    data[isin] = {"cik": sec.cik10(cik) if cik else None, "geprueft_am": on.isoformat()}
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Lucas Zuordnungen ISIN -> CIK der SEC (ADR 0002). Gepflegt mit\n"
        "# `stockagent sec map <ISIN> <CIK>|keine`. Vorrang vor OpenFIGI und Namensabgleich.\n"
    )
    path.write_text(header + yaml.safe_dump(data, sort_keys=True), encoding="utf-8")


# ------------------------------------------------------------------ Zuordnung


# Die SEC führt ADR-Programme der Depotbanken (Formular F-6) als eigene Melder mit "/ADR" im
# Namen und SIC 8880. Sie reichen keine Abschlüsse ein.
_ADR_HUELLE = re.compile(r"/ADR/?\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class Listing:
    isin: str
    name: str
    lei_name: str | None


def decide(
    listing: Listing,
    figi: openfigi.FigiResult | None,
    by_ticker: dict[str, sec.TickerEntry],
    by_name: dict[tuple[str, ...], list[sec.TickerEntry]],
    override: tuple[bool, str | None],
) -> store.IsinCik:
    """Zuordnung einer ISIN. Im Zweifel leer (Status `unsicher` oder `keine`), nie geraten."""
    row = _decide(listing, figi, by_ticker, by_name, override)
    return dataclasses.replace(row, figi_name=figi.name if figi else None)


def _decide(
    listing: Listing,
    figi: openfigi.FigiResult | None,
    by_ticker: dict[str, sec.TickerEntry],
    by_name: dict[tuple[str, ...], list[sec.TickerEntry]],
    override: tuple[bool, str | None],
) -> store.IsinCik:
    has_override, override_cik = override
    if has_override:
        if override_cik is None:
            return store.IsinCik(listing.isin, None, None, "manuell", "keine", "laut Luca")
        return store.IsinCik(listing.isin, override_cik, None, "manuell", "zugeordnet", "laut Luca")
    if figi is not None and figi.ticker:
        entry = by_ticker.get(figi.ticker)
        if entry is None:
            return store.IsinCik(
                listing.isin,
                None,
                figi.ticker,
                "openfigi",
                "keine",
                f"Ticker {figi.ticker} nicht in der Tickerliste der SEC (kein SEC-Melder, "
                "etwa ein ADR ohne eigene Berichte)",
            )
        if _ADR_HUELLE.search(entry.name):
            return store.IsinCik(
                listing.isin,
                None,
                figi.ticker,
                "openfigi",
                "keine",
                f"Ticker {figi.ticker} gehört nur zur ADR-Registrierung der Depotbank "
                f"({entry.name}), ohne eigene Abschlüsse bei der SEC",
            )
        names = [n for n in (listing.name, listing.lei_name, figi.name) if n]
        if any(names_plausibly_match(n, entry.name) for n in names):
            return store.IsinCik(
                listing.isin,
                entry.cik,
                figi.ticker,
                "openfigi",
                "zugeordnet",
                f"Ticker {figi.ticker} -> {entry.name}",
            )
        return store.IsinCik(
            listing.isin,
            None,
            figi.ticker,
            "openfigi",
            "unsicher",
            f"Ticker {figi.ticker} gehört laut SEC zu {entry.name}, Name passt nicht zu "
            f"{listing.name}",
        )
    # Rückfall: exakt gleicher Name (ohne Rechtsform) wie ein SEC-Melder, nur mit LEI-Namen
    tokens = tuple(name_tokens(listing.lei_name or ""))
    # Leere Namen (etwa nur chinesische Schrift oder nur Rechtsform) nie vergleichen
    if tokens:
        treffer = by_name.get(tokens, [])
        ciks = {t.cik for t in treffer}
        if len(ciks) == 1:
            t = treffer[0]
            return store.IsinCik(
                listing.isin,
                t.cik,
                None,
                "name",
                "zugeordnet",
                f"LEI-Name gleich SEC-Name {t.name}",
            )
        if len(ciks) > 1:
            return store.IsinCik(
                listing.isin,
                None,
                None,
                "name",
                "unsicher",
                f"LEI-Name passt zu mehreren SEC-Meldern: {sorted(ciks)}",
            )
    note = figi.note if figi else "nicht abgefragt"
    return store.IsinCik(listing.isin, None, None, "keine", "keine", note)


@dataclass
class MappingSummary:
    geprueft: int = 0
    abgefragt: int = 0
    status: Counter[str] = field(default_factory=Counter)


def map_isins(
    conn: Any,
    figi_client: openfigi.OpenFigiClient,
    tickers: list[sec.TickerEntry],
    overrides: dict[str, str | None],
    now: datetime,
    recheck_days: int,
    *,
    only: set[str] | None = None,
    progress: Progress = _noop,
    block: int = 100,
) -> MappingSummary:
    listings = [Listing(*row) for row in store.us_listings(conn, overrides)]
    if only is not None:
        listings = [li for li in listings if li.isin in only]
    known = store.load_isin_cik(conn)
    checked = dict(
        conn.execute("SELECT isin, checked_at FROM isin_cik").fetchall()  # naives UTC
    )
    grenze = (now - timedelta(days=recheck_days)).astimezone(UTC).replace(tzinfo=None)
    stale = [
        li
        for li in listings
        if li.isin in overrides or li.isin not in known or checked[li.isin] < grenze
    ]
    by_ticker = {t.ticker: t for t in tickers}
    by_name: dict[tuple[str, ...], list[sec.TickerEntry]] = defaultdict(list)
    for t in tickers:
        by_name[tuple(name_tokens(t.name))].append(t)
    # Gespeicherte Zuordnungen nach den aktuellen Regeln neu bewerten, ohne OpenFIGI zu fragen:
    # Der Ticker ist gespeichert. So wirken Regeländerungen sofort, und die Tickerliste der SEC
    # ist bei jedem Lauf aktuell.
    stale_isins = {li.isin for li in stale}
    neu = [
        decide(
            li,
            openfigi.FigiResult(
                li.isin,
                known[li.isin].ticker,
                known[li.isin].figi_name,
                "" if known[li.isin].ticker else known[li.isin].detail,
            ),
            by_ticker,
            by_name,
            (False, None),
        )
        for li in listings
        if li.isin not in stale_isins and known[li.isin].method in ("openfigi", "name", "keine")
    ]
    geaendert = [r for r in neu if r != known[r.isin]]
    if geaendert:
        store.save_isin_cik(conn, geaendert, now)
        progress(f"Nach aktuellen Regeln neu bewertet: {len(geaendert)} Zuordnungen geändert")
    to_query = [li.isin for li in stale if li.isin not in overrides]
    if to_query:
        progress(f"OpenFIGI: {len(to_query)} ISINs (etwa {len(to_query) // 250 + 1} Minuten)")
    # In Blöcken speichern, damit ein Abbruch nicht die ganze Arbeit verliert
    for start in range(0, len(stale), block):
        teil = stale[start : start + block]
        anfragen = [li.isin for li in teil if li.isin not in overrides]
        figi = {r.isin: r for r in figi_client.map(anfragen)} if anfragen else {}
        rows = [
            decide(
                li,
                figi.get(li.isin),
                by_ticker,
                by_name,
                (li.isin in overrides, overrides.get(li.isin)),
            )
            for li in teil
        ]
        store.save_isin_cik(conn, rows, now)
        if anfragen:
            progress(f"OpenFIGI {min(start + block, len(stale))}/{len(stale)}")
    summary = MappingSummary(geprueft=len(listings), abgefragt=len(to_query))
    for row in store.load_isin_cik(conn).values():
        if only is None or row.isin in only:
            summary.status[row.status] += 1
    return summary


# ------------------------------------------------------------------ Stammdaten und Werte


def isins_by_cik(conn: Any) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for row in store.load_isin_cik(conn).values():
        if row.cik and row.status == "zugeordnet":
            out[row.cik].append(row.isin)
    return out


def save_master_data(
    conn: Any, subs: sec.Submissions, ref_sha: str, retrieved: datetime, isins: list[str]
) -> None:
    store.save_issuer(
        conn,
        store.IssuerRow(
            issuer_id=sec.issuer_id(subs.cik),
            lei=store.listing_lei(conn, isins),
            cik=subs.cik,
            name=subs.name,
            country=subs.country,
            sector_sic=subs.sic,
            sic_description=subs.sic_description,
            fiscal_year_end=subs.fiscal_year_end,
            state_of_incorporation=subs.state_of_incorporation,
            business_address=subs.business_address,
            business_region=subs.business_region,
            entity_type=subs.entity_type,
            filer_category=subs.category,
            source="sec_submissions",
            source_sha256=ref_sha,
            retrieved_at=retrieved,
        ),
    )


def latest_annual(subs: sec.Submissions, as_of: datetime) -> sec.Filing | None:
    forms = ("10-K", "20-F", "40-F", "10-KT")
    kandidaten = [f for f in subs.filings.values() if f.form in forms and _published(f) <= as_of]
    return max(kandidaten, key=lambda f: (f.filing_date, f.accession), default=None)


def _published(f: sec.Filing) -> datetime:
    return sec.published_at(f.filing_date, f.accepted_at)


def load_report(client: sec.SecClient, cik: str, filing: sec.Filing) -> quality.Originalbericht:
    names = client.filing_files(cik, filing.accession)
    instance_name, cal_name = sec_xbrl.choose_files(names)
    instance, _ = client.filing_file(cik, filing.accession, instance_name)
    calc: list[sec_xbrl.Summation] = []
    if cal_name:
        cal, _ = client.filing_file(cik, filing.accession, cal_name)
        calc = sec_xbrl.parse_calculation(cal)
    return quality.Originalbericht(
        accession=filing.accession,
        form=filing.form,
        stichtag=filing.report_date or filing.filing_date,
        instance=sec_xbrl.parse_instance(instance),
        calculation=calc,
        url=client.filing_url(cik, filing.accession, instance_name),
    )


@dataclass
class LoadResult:
    isin: str
    issuer_id: str | None = None
    name: str | None = None
    facts: int = 0
    flags: Counter[str] = field(default_factory=Counter)
    error: str | None = None


def load_issuer_facts(
    conn: Any,
    client: sec.SecClient,
    cik: str,
    isins: list[str],
    paths: Paths,
    now: datetime,
) -> LoadResult:
    result = LoadResult(isin=isins[0], issuer_id=sec.issuer_id(cik))
    subs, ref = client.submissions(cik)
    save_master_data(conn, subs, ref.sha256, ref.retrieved_at, isins)
    result.name = subs.name
    parsed = client.companyfacts(cik, subs.filings)
    result.facts = store.replace_facts(conn, sec.issuer_id(cik), parsed.facts, parsed.documents)
    bericht = None
    filing = latest_annual(subs, now)
    report_error = None
    if filing is not None:
        try:
            bericht = load_report(client, cik, filing)
        except (FetchError, sec_xbrl.XbrlFormatError) as exc:
            report_error = f"Originalbericht {filing.accession} nicht lesbar: {exc}"
    issuer = sec.issuer_id(cik)
    cmap = concepts.load(paths.config)
    ctx = quality.Kontext(
        issuer_id=issuer,
        as_of=now,
        facts=store.pit_query(conn, as_of=now, issuer_id=issuer),
        restatements=store.restatements(conn, as_of=now, issuer_id=issuer),
        fiscal_year_end=subs.fiscal_year_end,
        skipped_units=parsed.skipped_units,
        skipped_forms=parsed.skipped_forms,
        bericht=bericht,
        bericht_facts=store.pit_query(
            conn, as_of=now, issuer_id=issuer, fassung="einreichung", accession=filing.accession
        )
        if filing
        else [],
        aktien_erstmeldung=store.pit_query(
            conn, as_of=now, issuer_id=issuer, concepts=[cmap["split_reihe"]], fassung="erste"
        ),
    )
    cfg = yaml.safe_load((paths.config / "quality.yaml").read_text("utf-8"))
    flags = quality.run(ctx, cmap, cfg)
    if report_error:
        flags.append(store.DqFlag(issuer, "DQ-05", "warnung", None, None, report_error))
    store.replace_dq_flags(conn, issuer, flags, now)
    result.flags = Counter(f.severity for f in flags)
    return result


# ------------------------------------------------------------------ Gesamtablauf


@dataclass
class UpdateResult:
    mapping: MappingSummary
    master_loaded: int = 0
    master_skipped: int = 0
    master_errors: list[str] = field(default_factory=list)
    loaded: list[LoadResult] = field(default_factory=list)


def update(
    paths: Paths,
    *,
    isins: list[str] | None = None,
    limit: int | None = None,
    refresh: bool = False,
    fetcher: Callable[..., bytes] = fetch,
    sleep: Callable[[float], None] = time.sleep,
    now: datetime | None = None,
    progress: Progress = _noop,
) -> UpdateResult:
    now = now or datetime.now(UTC)
    cfg = yaml.safe_load((paths.config / "sources.yaml").read_text("utf-8"))
    agent = sec.user_agent(paths.root, cfg["sec"]["user_agent_env"])
    client = sec.SecClient(
        cfg["sec"],
        agent,
        paths.raw,
        fetcher=fetcher,
        limiter=sec.RateLimiter(float(cfg["sec"]["max_requests_per_s"]), sleep=sleep),
        now=lambda: now,
    )
    figi_client = openfigi.OpenFigiClient(
        cfg["openfigi"],
        cfg["user_agent"],
        paths.raw,
        fetcher=fetcher,
        sleep=sleep,
        now=lambda: now,
    )
    conn = store.connect(paths.db)
    try:
        progress("SEC: Tickerliste")
        tickers, _ = client.tickers()
        only = {i.upper() for i in isins} if isins else None
        mapping = map_isins(
            conn,
            figi_client,
            tickers,
            load_overrides(overrides_path(paths)),
            now,
            int(cfg["openfigi"]["recheck_days"]),
            only=only,
            progress=progress,
        )
        result = UpdateResult(mapping)
        by_cik = isins_by_cik(conn)
        if only is not None:
            by_cik = {c: i for c, i in by_cik.items() if set(i) & only}
        # Werte nur für die Auswahl (Luca, 13.10.2026: alle erst in Schritt 5)
        selected = sorted(by_cik)
        if only is None:
            selected = selected[:limit] if limit else []
        fresh = {
            r[0]
            for r in conn.execute(
                "SELECT cik FROM issuers WHERE retrieved_at >= ?",
                [
                    (now - timedelta(days=int(cfg["sec"]["master_refresh_days"])))
                    .astimezone(UTC)
                    .replace(tzinfo=None)
                ],
            ).fetchall()
        }
        for n, cik in enumerate(sorted(by_cik)):
            if cik in selected:
                continue  # Stammdaten kommen beim Laden der Werte mit
            if cik in fresh and not refresh:
                result.master_skipped += 1
                continue
            if n % 100 == 0:
                progress(f"SEC-Stammdaten {n}/{len(by_cik)}")
            try:
                subs, ref = client.submissions(cik)
                save_master_data(conn, subs, ref.sha256, ref.retrieved_at, by_cik[cik])
                result.master_loaded += 1
            except (FetchError, sec.SecFormatError) as exc:
                result.master_errors.append(f"{cik}: {exc}")
        for cik in selected:
            progress(f"SEC-Werte {cik} ({', '.join(by_cik[cik])})")
            try:
                result.loaded.append(
                    load_issuer_facts(conn, client, cik, sorted(by_cik[cik]), paths, now)
                )
            except (FetchError, sec.SecFormatError) as exc:
                result.loaded.append(
                    LoadResult(isin=by_cik[cik][0], issuer_id=sec.issuer_id(cik), error=str(exc))
                )
        if only is not None:
            for isin in sorted(only - {i for v in by_cik.values() for i in v}):
                row = store.load_isin_cik(conn).get(isin)
                why = f"{row.status}: {row.detail}" if row else "keine US-ISIN im Universum"
                result.loaded.append(LoadResult(isin=isin, error=f"keine CIK ({why})"))
        return result
    finally:
        conn.close()
