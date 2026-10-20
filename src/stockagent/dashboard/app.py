"""Dashboard als Bedienzentrale (SPEC 13.5, ADR 0004).

Ein lokaler Server nur auf 127.0.0.1. Er zeigt die Liste aller Aktien mit Filtern, die Seite
jeder Aktie mit Notenzerlegung und startet das Bewerten im Hintergrund. Er schreibt nur nach
`state/` (Stern, Notizen, Trade-Republic-Prüfung) und über die normalen Abläufe in die
Datenbank. Anfragen mit fremdem Host oder fremder Herkunft werden abgelehnt (Schutz gegen
DNS-Rebinding und fremde Webseiten).

Kein Sprachmodell: Freitext wird über eine feste Wortliste in Filter übersetzt (SPEC 9.9, die
Übersetzung mit `claude -p` folgt in Schritt 11).
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
import subprocess
import threading
import traceback
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import yaml

from stockagent import bewertung, orchestrator, tiers, tr_checks
from stockagent.core import sektoren
from stockagent.data import store
from stockagent.paths import Paths

ERLAUBTE_HOSTS = {"127.0.0.1", "localhost"}
MAX_ZEILEN = 500


# ------------------------------------------------------------------ Merkliste und Notizen


def _yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text("utf-8")) or {}
    return dict(data)


def _yaml_schreiben(path: Path, kopf: str, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join([kopf, yaml.safe_dump(data, sort_keys=True, allow_unicode=True)]), "utf-8"
    )


@dataclass
class Merkliste:
    root: Path

    @property
    def stern_datei(self) -> Path:
        return self.root / "state" / "watchlist.yaml"

    @property
    def notiz_datei(self) -> Path:
        return self.root / "state" / "notes.yaml"

    def sterne(self) -> set[str]:
        return set(_yaml(self.stern_datei).get("isins", []))

    def stern(self, isin: str, an: bool) -> None:
        s = self.sterne()
        s = s | {isin} if an else s - {isin}
        _yaml_schreiben(self.stern_datei, "# Beobachtungsliste (Dashboard)", {"isins": sorted(s)})

    def notizen(self) -> dict[str, str]:
        return {str(k): str(v) for k, v in _yaml(self.notiz_datei).items()}

    def notiz(self, isin: str, text: str) -> None:
        n = self.notizen()
        if text.strip():
            n[isin] = text.strip()
        else:
            n.pop(isin, None)
        _yaml_schreiben(self.notiz_datei, "# Notizen je Titel (Dashboard)", n)


# ------------------------------------------------------------------ Liste


@dataclass(frozen=True)
class Zeile:
    isin: str
    name: str
    land: str
    region: str
    art: str
    tier: int
    branche: str
    unterbranche: str
    groesse: str
    note: str
    konfidenz: str
    risiko: str
    kategorie: str
    score: str
    tr: str
    stern: bool
    datenlage: str


class Daten:
    """Liste aller Aktien, einmal geladen und nach jedem Bewerten neu."""

    def __init__(self, paths: Paths) -> None:
        self.paths = paths
        self.lock = threading.Lock()
        self.zeilen: list[Zeile] = []
        self.stand = ""
        self.neu_laden()

    def neu_laden(self) -> None:
        cfg_sec = yaml.safe_load((self.paths.config / "sectors.yaml").read_text("utf-8"))
        cfg_sc = yaml.safe_load((self.paths.config / "scoring.yaml").read_text("utf-8"))
        regionen = cfg_sc["vergleichsgruppe"]["regionen"]
        merk = Merkliste(self.paths.root)
        sterne = merk.sterne()
        checks = tr_checks.load(self.paths.tr_checks)
        stufen = tiers.stufen_aller(self.paths)
        conn = store.connect(self.paths.db)
        try:
            rows = conn.execute(
                "SELECT l.isin, l.name, l.country, l.is_receipt, i.sector_sic, m.cik "
                "FROM listings l LEFT JOIN isin_cik m ON m.isin = l.isin "
                "AND m.status = 'zugeordnet' "
                "LEFT JOIN issuers i ON i.issuer_id = 'sec:' || m.cik WHERE l.listed "
                "ORDER BY l.name"
            ).fetchall()
            grades = {g.isin: g for g in store.load_grades(conn)}
            stand = conn.execute("SELECT max(computed_at) FROM grades").fetchone()
        finally:
            conn.close()
        zeilen = []
        for isin, name, land, receipt, sic, cik in rows:
            b = sektoren.branche(int(sic) if sic and str(sic).isdigit() else None, cfg_sec)
            g = grades.get(isin)
            c = checks.get(isin)
            zeilen.append(
                Zeile(
                    isin=isin,
                    name=name,
                    land=land or "",
                    region=sektoren.region(land, regionen) or "",
                    art="Hinterlegungsschein" if receipt else "Aktie",
                    tier=stufen.get(isin, (4, []))[0],
                    branche=b.haupt_name if b else "",
                    unterbranche=b.unter_name if b else "",
                    groesse=(g.groessenklasse or "") if g else "",
                    note=g.grade if g else "",
                    konfidenz=(g.konfidenz or "") if g else "",
                    risiko=(g.risiko or "") if g else "",
                    kategorie=(g.kategorie or "") if g else "",
                    score=str(g.score) if g and g.score is not None else "",
                    tr=c.status.value if c else "ungeprueft",
                    stern=isin in sterne,
                    datenlage="SEC" if cik else "keine strukturierten Daten",
                )
            )
        with self.lock:
            self.zeilen = zeilen
            self.stand = f"{stand[0]:%d.%m.%Y %H:%M}" if stand and stand[0] else ""


FILTER = (
    "tier",
    "land",
    "region",
    "branche",
    "groesse",
    "note",
    "konfidenz",
    "risiko",
    "kategorie",
    "tr",
    "datenlage",
    "art",
)


def _passt(z: Zeile, f: dict[str, str]) -> bool:
    for k in FILTER:
        if f.get(k) and str(getattr(z, k)) != f[k]:
            return False
    if f.get("stern") == "1" and not z.stern:
        return False
    if f.get("bewertet") == "1" and not z.note:
        return False
    q = f.get("q", "").strip().lower()
    return not q or q in z.name.lower() or q.upper() == z.isin


def liste(daten: Daten, f: dict[str, str]) -> dict[str, Any]:
    with daten.lock:
        alle = list(daten.zeilen)
    treffer = [z for z in alle if _passt(z, f)]
    facetten: dict[str, list[tuple[str, int]]] = {}
    for k in FILTER:
        ohne = {kk: v for kk, v in f.items() if kk != k}
        zaehler = Counter(str(getattr(z, k)) for z in alle if _passt(z, ohne))
        facetten[k] = sorted(zaehler.items(), key=lambda x: (-x[1], x[0]))
    bewertet = sum(1 for z in alle if z.note and z.note != "N")
    return {
        "anzahl": len(treffer),
        "gesamt": len(alle),
        "bewertet": bewertet,
        "stand": daten.stand,
        "zeilen": [asdict(z) for z in treffer[:MAX_ZEILEN]],
        "facetten": facetten,
    }


# ------------------------------------------------------------------ Freitext (Wortliste)


LAENDER = {
    "deutschland": "DE",
    "usa": "US",
    "amerika": "US",
    "vereinigte staaten": "US",
    "frankreich": "FR",
    "griechenland": "GR",
    "italien": "IT",
    "spanien": "ES",
    "schweiz": "CH",
    "österreich": "AT",
    "niederlande": "NL",
    "großbritannien": "GB",
    "uk": "GB",
    "japan": "JP",
    "kanada": "CA",
    "china": "CN",
    "schweden": "SE",
    "dänemark": "DK",
    "norwegen": "NO",
    "finnland": "FI",
    "belgien": "BE",
    "irland": "IE",
    "portugal": "PT",
    "polen": "PL",
    "australien": "AU",
    "hongkong": "HK",
}
REGIONEN = {
    "europa": "europa",
    "nordamerika": "nordamerika",
    "asien": "asien_pazifik",
    "schwellenländer": "schwellenlaender",
}

# Umgangssprachliche Wörter für Hauptbranchen (Namen aus config/sectors.yaml)
BRANCHEN_WOERTER = {
    "technologie": "Informationstechnik",
    "tech": "Informationstechnik",
    "software": "Informationstechnik",
    "halbleiter": "Informationstechnik",
    "banken": "Finanzen",
    "versicherungen": "Finanzen",
    "pharma": "Gesundheit",
    "medizin": "Gesundheit",
    "rohstoffe": "Grundstoffe",
    "öl": "Energie",
    "telekom": "Kommunikation",
}


def freitext(text: str, daten: Daten) -> dict[str, str]:
    """Einfache Sätze in Filter: Tier, Land, Region, Branche, Note. Unbekanntes wird Suche."""
    t = text.lower()
    f: dict[str, str] = {}
    if m := re.search(r"tier[ -]?([1-4])", t):
        f["tier"] = m.group(1)
        t = t.replace(m.group(0), " ")
    if m := re.search(r"note ([a-e])\b", t):
        f["note"] = m.group(1).upper()
        t = t.replace(m.group(0), " ")
    for wort, code in LAENDER.items():
        if re.search(rf"\b{re.escape(wort)}\b", t):
            f["land"] = code
            t = t.replace(wort, " ")
    for wort, code in REGIONEN.items():
        if wort in t:
            f["region"] = code
            t = t.replace(wort, " ")
    with daten.lock:
        branchen = {z.branche for z in daten.zeilen if z.branche}
    for b in sorted(branchen, key=len, reverse=True):
        if b.lower() in t:
            f["branche"] = b
            t = t.replace(b.lower(), " ")
    for wort, b in BRANCHEN_WOERTER.items():
        if "branche" not in f and b in branchen and re.search(rf"\b{wort}\b", t):
            f["branche"] = b
            t = re.sub(rf"\b{wort}\b", " ", t)
    rest = re.sub(r"\b(aktien|aus|der|die|das|branche|und|mit|bewerte|sie|zeige)\b", " ", t)
    rest = " ".join(rest.replace(",", " ").split())
    if rest:
        f["q"] = rest
    return f


# ------------------------------------------------------------------ Hintergrundaufgaben


@dataclass
class Aufgabe:
    id: str
    art: str
    isin: str | None
    status: str = "läuft"
    meldungen: list[str] = field(default_factory=list)
    ergebnis: dict[str, Any] | None = None


class Aufgaben:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.alle: dict[str, Aufgabe] = {}

    def starte(self, art: str, isin: str | None, arbeit: Any) -> Aufgabe:
        a = Aufgabe(uuid.uuid4().hex[:8], art, isin)
        with self.lock:
            self.alle[a.id] = a

        def lauf() -> None:
            try:
                a.ergebnis = arbeit(lambda m: a.meldungen.append(m))
                a.status = "fertig"
            except Exception as exc:
                a.meldungen.append(f"Fehler: {exc}")
                a.meldungen.append(traceback.format_exc(limit=3))
                a.status = "fehler"

        threading.Thread(target=lauf, daemon=True).start()
        return a


# ------------------------------------------------------------------ Tiefenanalyse (Bauschritt 6)

RUN_ID = re.compile(r"^[0-9T:-]+Z_[A-Z0-9]{12}$")
# Rechte des Hintergrundlaufs: nur das CLI, Lesen, Schreiben unter runs/, Subagents. Die Rechte
# der Subagents selbst stehen in ihrem Frontmatter (.claude/agents/).
ERLAUBTE_WERKZEUGE = [
    "Bash(uv run stockagent *)",
    "Read",
    "Grep",
    "Write(./runs/**)",
    "Agent",
    "WebSearch",
    "WebFetch",
]


def claude_befehl(isin: str) -> list[str]:
    """`claude -p` im Hintergrund über Lucas Abo (SPEC 13.5). Rechte nur über die Liste oben."""
    return [
        shutil.which("claude") or "claude",
        "-p",
        f"/analyze-stock {isin}",
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "dontAsk",
        "--allowedTools",
        *ERLAUBTE_WERKZEUGE,
        "--max-turns",
        "300",
    ]


class Analysen:
    """Eine Tiefenanalyse zur Zeit, weitere warten in `state/analysis_queue.yaml`."""

    def __init__(self, paths: Paths, starter: Any = subprocess.Popen) -> None:
        self.paths = paths
        self.starter = starter
        self.lock = threading.Lock()
        self.laufend: dict[str, Any] = {}  # ISIN -> Prozess

    @property
    def datei(self) -> Path:
        return self.paths.root / "state" / "analysis_queue.yaml"

    def warteschlange(self) -> list[str]:
        return [str(x) for x in _yaml(self.datei).get("isins", [])]

    def _aktiv(self) -> list[str]:
        return [i for i, p in self.laufend.items() if p.poll() is None]

    def starten(self, isin: str) -> dict[str, Any]:
        with self.lock:
            if isin in self._aktiv() or isin in self.warteschlange():
                return {"status": "schon_geplant"}
            if self._aktiv():
                _yaml_schreiben(
                    self.datei,
                    "# Warteschlange Tiefenanalysen",
                    {"isins": [*self.warteschlange(), isin]},
                )
                return {"status": "wartet", "vor_dir": len(self.warteschlange()) - 1}
            if shutil.which("claude") is None and self.starter is subprocess.Popen:
                return {"status": "fehler", "grund": "Claude Code (claude) nicht gefunden"}
            log = self.paths.runs / "_dashboard"
            log.mkdir(parents=True, exist_ok=True)
            with (log / f"{isin}.jsonl").open("ab") as fh:
                self.laufend[isin] = self.starter(
                    claude_befehl(isin),
                    cwd=self.paths.root,
                    stdout=fh,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,  # läuft weiter, wenn Browser oder Server schließen
                )
            return {"status": "gestartet"}

    def weiter(self) -> None:
        """Nächsten Titel der Warteschlange starten, wenn nichts läuft."""
        with self.lock:
            schlange = self.warteschlange()
            if self._aktiv() or not schlange:
                return
            _yaml_schreiben(self.datei, "# Warteschlange Tiefenanalysen", {"isins": schlange[1:]})
        self.starten(schlange[0])

    def stand(self, isin: str) -> dict[str, Any]:
        self.weiter()
        laeufe = [z for z in orchestrator.laufende(self.paths) if z.isin == isin]
        letzter = max(laeufe, key=lambda z: z.erstellt) if laeufe else None
        return {
            "prozess": "läuft" if isin in self._aktiv() else None,
            "wartet": isin in self.warteschlange(),
            "lauf": orchestrator.fortschritt(letzter) if letzter else None,
            "bericht": f"/bericht/{letzter.run_id}"
            if letzter and (self.paths.runs / letzter.run_id / "report.html").exists()
            else None,
        }


# ------------------------------------------------------------------ Server


def titel_detail(paths: Paths, isin: str) -> dict[str, Any]:
    conn = store.connect(paths.db)
    try:
        info = conn.execute(
            "SELECT name, country, wkn, is_receipt FROM listings WHERE isin = ?", [isin]
        ).fetchone()
        g = store.load_grade(conn, isin)
        cik = conn.execute(
            "SELECT cik FROM isin_cik WHERE isin = ? AND status = 'zugeordnet'", [isin]
        ).fetchone()
        issuer = f"sec:{cik[0]}" if cik and cik[0] else None
        kennzahlen = []
        hinweise = []
        if issuer:
            lauf = store.load_metric_run(conn, issuer)
            if lauf:
                for r in store.load_metrics(conn, issuer):
                    if r.period_end == lauf[2] and r.statistik in ("wert", "aktuell", "ttm"):
                        kennzahlen.append(
                            {
                                "id": r.metric_id,
                                "statistik": r.statistik,
                                "wert": str(r.value) if r.value is not None else None,
                                "grund": r.grund,
                                "vermerke": list(r.vermerke),
                            }
                        )
            hinweise = [
                {"regel": h.regel, "an": h.an_agent, "detail": h.detail}
                for h in store.load_hinweise(conn, issuer)
            ]
        kurs = store.price_on_or_before(conn, isin, datetime.now(UTC).date())
    finally:
        conn.close()
    merk = Merkliste(paths.root)
    return {
        "isin": isin,
        "name": info[0] if info else isin,
        "land": info[1] if info else "",
        "wkn": info[2] if info else "",
        "hinterlegungsschein": bool(info[3]) if info else False,
        "note": asdict(g) if g else None,
        "detail": json.loads(g.detail_json) if g and g.detail_json else None,
        "kennzahlen": kennzahlen,
        "hinweise": hinweise,
        "kurs": {"datum": kurs.date.isoformat(), "wert": str(kurs.close), "waehrung": kurs.currency}
        if kurs
        else None,
        "stern": isin in merk.sterne(),
        "notiz": merk.notizen().get(isin, ""),
        "tr": tr_checks.load(paths.tr_checks).get(isin).status.value  # type: ignore[union-attr]
        if isin in tr_checks.load(paths.tr_checks)
        else "ungeprueft",
    }


def handler_fuer(
    paths: Paths, daten: Daten, aufgaben: Aufgaben, analysen: Analysen | None = None
) -> type[BaseHTTPRequestHandler]:
    seite = files("stockagent.dashboard").joinpath("template.html").read_text("utf-8")
    tief = analysen or Analysen(paths)

    class Handler(BaseHTTPRequestHandler):
        server_version = "stockagent"

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _erlaubt(self) -> bool:
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ERLAUBTE_HOSTS:
                return False
            herkunft = self.headers.get("Origin")
            return not herkunft or urlparse(herkunft).hostname in ERLAUBTE_HOSTS

        def _json(self, data: Any, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _text(self, body: str, typ: str) -> None:
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", typ)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _filter(self) -> dict[str, str]:
            q = parse_qs(urlparse(self.path).query)
            return {k: v[0] for k, v in q.items() if v}

        def do_GET(self) -> None:
            if not self._erlaubt():
                self._json({"fehler": "nur lokal"}, HTTPStatus.FORBIDDEN)
                return
            pfad = urlparse(self.path).path
            if pfad == "/":
                self._text(seite, "text/html; charset=utf-8")
            elif pfad == "/api/liste":
                self._json(liste(daten, self._filter()))
            elif pfad == "/api/freitext":
                self._json(freitext(self._filter().get("text", ""), daten))
            elif pfad.startswith("/api/titel/"):
                self._json(titel_detail(paths, pfad.rsplit("/", 1)[1].upper()))
            elif pfad.startswith("/api/aufgabe/"):
                a = aufgaben.alle.get(pfad.rsplit("/", 1)[1])
                self._json(asdict(a) if a else {"fehler": "unbekannt"})
            elif pfad.startswith("/api/analyse/"):
                self._json(tief.stand(pfad.rsplit("/", 1)[1].upper()))
            elif pfad.startswith("/bericht/"):
                run_id = pfad.rsplit("/", 1)[1]
                datei = paths.runs / run_id / "report.html"
                if RUN_ID.match(run_id) and datei.exists():
                    self._text(datei.read_text("utf-8"), "text/html; charset=utf-8")
                else:
                    self._json({"fehler": "nicht gefunden"}, HTTPStatus.NOT_FOUND)
            elif pfad == "/api/export.csv":
                buf = io.StringIO()
                w = csv.writer(buf, delimiter=";")
                felder = list(Zeile.__dataclass_fields__)
                w.writerow(felder)
                for z in liste(daten, self._filter())["zeilen"]:
                    w.writerow([z[f] for f in felder])
                self._text(buf.getvalue(), "text/csv; charset=utf-8")
            else:
                self._json({"fehler": "nicht gefunden"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if not self._erlaubt():
                self._json({"fehler": "nur lokal"}, HTTPStatus.FORBIDDEN)
                return
            laenge = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(laenge) or b"{}") if laenge else {}
            pfad = urlparse(self.path).path
            teile = pfad.strip("/").split("/")
            isin = teile[-1].upper() if len(teile) >= 3 else ""
            merk = Merkliste(paths.root)
            if pfad.startswith("/api/bewerten/"):

                def arbeit(melde: Any) -> dict[str, Any]:
                    erg = bewertung.bewerten(paths, isin, progress=melde)
                    daten.neu_laden()
                    return {"note": erg.note, "grund": erg.grund}

                self._json(asdict(aufgaben.starte("bewerten", isin, arbeit)))
            elif pfad.startswith("/api/analyse/"):
                self._json(tief.starten(isin))
            elif pfad.startswith("/api/stern/"):
                merk.stern(isin, bool(body.get("an")))
                daten.neu_laden()
                self._json({"ok": True})
            elif pfad.startswith("/api/notiz/"):
                merk.notiz(isin, str(body.get("text", "")))
                self._json({"ok": True})
            elif pfad.startswith("/api/tr/"):
                handelbar = bool(body.get("handelbar"))
                tr_checks.record(paths.tr_checks, isin, handelbar, datetime.now(UTC).date())
                daten.neu_laden()
                self._json({"ok": True})
            else:
                self._json({"fehler": "nicht gefunden"}, HTTPStatus.NOT_FOUND)

    return Handler


def server(paths: Paths, port: int = 8765) -> ThreadingHTTPServer:
    daten = Daten(paths)
    return ThreadingHTTPServer(("127.0.0.1", port), handler_fuer(paths, daten, Aufgaben()))
