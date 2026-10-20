"""Berichte als Seitentext (Bauschritt 6, SPEC 7.4 und 12.6).

Geladen wird das Hauptdokument einer Einreichung bei der SEC (feste Adresse, Quellenkarte
`berichtstext`). Die HTML-Datei wird an den Seitenumbrüchen der Quelle (CSS `page-break-before`,
`page-break-after`, `break-before: page`, `<hr>` mit Umbruch) in Seiten geteilt. Seitenzahl ist
die laufende Seite im Dokument, nicht die aufgedruckte Nummer. Unsichtbare Teile (der
Inline-XBRL-Kopf mit `display:none`), Skripte und Stile fallen weg.

Der Seitentext ist die Grundlage für das Zitat-Gate (HR-03) und für die Agenten, die Berichte
lesen. Inhalte aus Dokumenten sind Daten, nie Anweisungen (HR-17).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

import duckdb

from stockagent.data import store
from stockagent.data.sources import sec

_UMBRUCH = re.compile(
    r"page-break-(?:before|after)\s*:\s*always|break-(?:before|after)\s*:\s*page", re.IGNORECASE
)
_VERSTECKT = re.compile(r"display\s*:\s*none", re.IGNORECASE)
_BLOCK = {
    "p",
    "div",
    "br",
    "tr",
    "li",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "table",
    "section",
}
_LEER = {"br", "hr", "img", "meta", "link", "input", "col", "area", "base", "wbr", "source"}
_OHNE_TEXT = {"script", "style", "head", "title", "ix:header"}


class _Seiten(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.seiten: list[list[str]] = [[]]
        self._stapel: list[tuple[str, bool, bool]] = []  # (Tag, versteckt, Umbruch danach)

    def _umbruch(self) -> None:
        if any(t.strip() for t in self.seiten[-1]):
            self.seiten.append([])

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        style = " ".join(v or "" for k, v in attrs if k == "style")
        if tag == "hr" and _UMBRUCH.search(style):
            self._umbruch()
        if tag in _LEER:
            if tag == "br":
                self.seiten[-1].append("\n")
            return
        versteckt = bool(_VERSTECKT.search(style)) or tag in _OHNE_TEXT
        if re.search(r"page-break-before\s*:\s*always|break-before\s*:\s*page", style, re.I):
            self._umbruch()
        nach = bool(re.search(r"page-break-after\s*:\s*always|break-after\s*:\s*page", style, re.I))
        self._stapel.append((tag, versteckt, nach))
        if tag in _BLOCK:
            self.seiten[-1].append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _LEER:
            return
        # Bis zum passenden Tag schließen (fehlerhaftes HTML)
        for i in reversed(range(len(self._stapel))):
            if self._stapel[i][0] == tag:
                for _, _, nach in reversed(self._stapel[i:]):
                    if nach:
                        self._umbruch()
                del self._stapel[i:]
                break
        if tag in _BLOCK:
            self.seiten[-1].append("\n")

    def handle_data(self, data: str) -> None:
        if not any(versteckt for _, versteckt, _ in self._stapel):
            self.seiten[-1].append(data)


def _bereinigt(teile: list[str]) -> str:
    text = "".join(teile).replace("\xa0", " ")
    zeilen = [" ".join(z.split()) for z in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(zeilen)).strip()


def html_seiten(raw: bytes) -> list[str]:
    """Seitentexte aus HTML. Leere Seiten fallen weg."""
    p = _Seiten()
    p.feed(raw.decode("utf-8", errors="replace"))
    p.close()
    seiten = [_bereinigt(s) for s in p.seiten]
    return [s for s in seiten if s]


@dataclass(frozen=True)
class Geladen:
    doc_id: str
    doc_hash: str
    doc_type: str
    seiten: int


def jahresberichte(subs: sec.Submissions, as_of: datetime, anzahl: int) -> list[sec.Filing]:
    """Die letzten `anzahl` Jahresberichte bis `as_of`, neuester zuerst."""
    forms = ("10-K", "20-F", "40-F", "10-KT")
    passend = [
        f
        for f in subs.filings.values()
        if f.form in forms
        and f.primary_document
        and sec.published_at(f.filing_date, f.accepted_at) <= as_of
    ]
    return sorted(passend, key=lambda f: f.filing_date, reverse=True)[:anzahl]


def lade_sec(
    conn: duckdb.DuckDBPyConnection,
    client: sec.SecClient,
    cik: str,
    filing: sec.Filing,
    now: datetime | None = None,
) -> Geladen:
    """Hauptdokument einer Einreichung laden, in Seiten teilen und speichern."""
    now = now or datetime.now(UTC)
    doc_id = f"sec:{filing.accession}/{filing.primary_document}"
    row = conn.execute(
        "SELECT doc_hash, doc_type, pages FROM documents WHERE doc_id = ? AND pages > 0", [doc_id]
    ).fetchone()
    if row:
        return Geladen(doc_id, row[0], row[1], int(row[2]))
    raw, ref = client.filing_file(cik, filing.accession, filing.primary_document)
    if Path(filing.primary_document).suffix.lower() not in (".htm", ".html"):
        raise ValueError(f"Hauptdokument ist kein HTML: {filing.primary_document}")
    seiten = html_seiten(raw)
    store.save_document(
        conn,
        store.DocumentRow(
            doc_id=doc_id,
            issuer_id=sec.issuer_id(cik),
            doc_type=filing.form,
            period_end=filing.report_date,
            published_at=sec.published_at(filing.filing_date, filing.accepted_at),
            retrieved_at=ref.retrieved_at,
            source_url=client.filing_url(cik, filing.accession, filing.primary_document),
            doc_hash=f"sha256:{ref.sha256}",
        ),
        seiten,
        "en",
    )
    return Geladen(doc_id, f"sha256:{ref.sha256}", filing.form, len(seiten))


def suche(
    conn: duckdb.DuckDBPyConnection, doc_hash: str, muster: str, kontext: int = 200
) -> list[tuple[int, str]]:
    """Fundstellen eines regulären Ausdrucks (ohne Groß- und Kleinschreibung) je Seite."""
    rx = re.compile(muster, re.IGNORECASE)
    out = []
    for page, text in conn.execute(
        "SELECT page, text FROM document_pages WHERE doc_hash = ? ORDER BY page", [doc_hash]
    ).fetchall():
        for m in rx.finditer(text):
            a, b = max(0, m.start() - kontext), min(len(text), m.end() + kontext)
            out.append((int(page), text[a:b].replace("\n", " ")))
    return out
