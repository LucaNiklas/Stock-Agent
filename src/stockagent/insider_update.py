"""Insidergeschäfte laden (Bauschritt 9, SPEC 3.8, 7.3, Abteilung Recherche).

Je angefragter ISIN mit SEC-Melder: Einreichungsliste (Submissions), daraus die Form-4-Meldungen
der letzten `jahre` Jahre (höchstens `max_meldungen`), jede noch nicht gelesene als XML laden,
Geschäfte in `insider_tx` speichern. Rohdateien mit SHA-256 in `data/raw/`. Gelesene Meldungen
werden nicht erneut geladen.

Deutschland (BaFin) fehlt: `portal.mvp.bafin.de` ist in dieser Umgebung gesperrt (ADR 0012).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from stockagent import metrics_update
from stockagent.data import store
from stockagent.data.http import FetchError, fetch
from stockagent.data.sources import form4, sec
from stockagent.paths import Paths

Progress = Callable[[str], None]
FORMEN = ("4", "4/A")


def _noop(_: str) -> None:
    pass


@dataclass
class InsiderErgebnis:
    isin: str
    issuer_id: str | None = None
    meldungen: int = 0
    neu: int = 0
    geschaefte: int = 0
    fehler: str | None = None


def update(
    paths: Paths,
    isins: list[str],
    *,
    fetcher: Callable[..., bytes] = fetch,
    now: datetime | None = None,
    progress: Progress = _noop,
    root: Path | None = None,
) -> list[InsiderErgebnis]:
    now = now or datetime.now(UTC)
    cfg = yaml.safe_load((paths.config / "sources.yaml").read_text("utf-8"))["sec"]
    fcfg = cfg["form4"]
    client = sec.SecClient(
        cfg,
        sec.user_agent(root or paths.root, cfg["user_agent_env"]),
        paths.raw,
        fetcher=fetcher,
        now=lambda: now,
    )
    seit = (now - timedelta(days=365 * int(fcfg["jahre"]))).date()
    out = []
    conn = store.connect(paths.db)
    try:
        for isin in dict.fromkeys(i.upper() for i in isins):
            erg = InsiderErgebnis(isin)
            out.append(erg)
            iid = metrics_update.issuer_for_isin(conn, isin)
            if iid is None or not iid.startswith("sec:"):
                erg.fehler = "kein SEC-Melder (Form 4 gibt es nur in den USA)"
                continue
            erg.issuer_id = iid
            cik = iid.removeprefix("sec:")
            try:
                sub, _ = client.submissions(cik)
            except (FetchError, sec.SecFormatError) as exc:
                erg.fehler = str(exc)
                continue
            meldungen = sorted(
                (f for f in sub.filings.values() if f.form in FORMEN and f.filing_date >= seit),
                key=lambda f: f.filing_date,
                reverse=True,
            )[: int(fcfg["max_meldungen"])]
            erg.meldungen = len(meldungen)
            bekannt = store.insider_filings_loaded(conn, iid)
            neu = [f for f in meldungen if f.accession not in bekannt]
            for nr, f in enumerate(neu, start=1):
                if nr % 25 == 1:
                    progress(f"{isin}: Form 4 {nr} bis {min(nr + 24, len(neu))} von {len(neu)}")
                name = form4.xml_name(f.primary_document)
                url = client.filing_url(cik, f.accession, name)
                try:
                    raw, ref = client.get(url)
                    rows = form4.parse_form4(
                        raw,
                        issuer_id=iid,
                        accession=f.accession,
                        veroeffentlicht=sec.published_at(f.filing_date, f.accepted_at),
                        raw_sha256=ref.sha256,
                        quelle=url,
                    )
                except (FetchError, form4.Form4FormatError) as exc:
                    store.save_insider(conn, f.accession, iid, [], now, fehler=str(exc)[:500])
                    continue
                store.save_insider(conn, f.accession, iid, rows, now)
                erg.neu += 1
                erg.geschaefte += len(rows)
    finally:
        conn.close()
    return out
