"""Dashboard als Bedienzentrale (SPEC 13.3, 13.5, ADR 0004, ADR 0014).

Ein lokaler Server nur auf 127.0.0.1. Er zeigt die Liste aller Aktien mit Filtern, die Seite
jeder Aktie mit Notenzerlegung, die Ansichten Änderungen, Karte, Vergleich, Historie, Methodik
und Eskalationen. Er bewertet im Hintergrund und startet Tiefenanalysen über Claude Code. Er
schreibt nur nach `state/` und `runs/` und über die normalen Abläufe in die Datenbank. Anfragen
mit fremdem Host oder fremder Herkunft werden abgelehnt (Schutz gegen DNS-Rebinding und fremde
Webseiten).

Suche in eigenen Worten (SPEC 9.9): erst die feste Wortliste, dann `claude -p` ohne Werkzeuge,
nur mit Werten aus den Listen (`anfrage.py`). „Alle bewerten“ zeigt zuerst den Laufplan und
startet erst nach Bestätigung (`lauf.py`).
"""

from __future__ import annotations

import csv
import io
import json
import re
import subprocess
import threading
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from typing import Any
from urllib.parse import parse_qs, urlparse

from stockagent import (
    anfrage,
    bewertung,
    claude_cli,
    eskalationen,
    historie,
    lauf,
    orchestrator,
    tr_checks,
)
from stockagent.data import store
from stockagent.paths import Paths
from stockagent.titelliste import (
    MAX_ZEILEN,
    Daten,
    Merkliste,
    Zeile,
    karte,
    liste,
    lockerungen,
    passt,
    yaml_schreiben,
)

__all__ = ["MAX_ZEILEN", "Daten", "Merkliste", "Zeile", "liste"]

ERLAUBTE_HOSTS = {"127.0.0.1", "localhost"}
ERLAUBTE_WERKZEUGE = claude_cli.ERLAUBTE_WERKZEUGE
claude_befehl = claude_cli.analyse_befehl
LAUF_ID = re.compile(r"^[0-9T:-]+Z_lauf$")
RUN_ID = re.compile(r"^[0-9T:-]+Z_[A-Z0-9]{12}$")


# ------------------------------------------------------------------ Freitext (SPEC 9.9)


def freitext(
    text: str,
    daten: Daten,
    vok: anfrage.Vokabular | None = None,
    modell: anfrage.Modell | None = None,
) -> dict[str, Any]:
    """Satz in Filter. Gespeicherte Ansicht mit diesem Namen zuerst, dann Wortliste, dann
    Modell. Antwort mit verstandenem Filter, Schaltflächen, Trefferzahl und bei null Treffern
    dem engsten lockernden Vorschlag."""
    vok = vok or anfrage.Vokabular.laden(daten.paths)
    gespeichert = anfrage.ansicht(daten.paths, text)
    if gespeichert is not None:
        a = anfrage.aus_filter(gespeichert, vok, "ansicht")
        v = anfrage.Verstanden(a)
        filter_ = gespeichert
    else:

        def namens_treffer(q: str) -> int:
            return sum(1 for z in daten.zeilen if passt(z, {"q": q}, daten.stile))

        v = anfrage.uebersetzen(text, vok, namens_treffer=namens_treffer, modell=modell)
        filter_ = anfrage.als_filter(v.anfrage, vok)
    antwort: dict[str, Any] = {
        "ok": v.ok,
        "abgelehnt": v.abgelehnt,
        "hinweise": v.hinweise,
        "rest": v.rest,
        "weg": v.anfrage.weg,
        "filter": filter_,
        "schaltflaechen": anfrage.beschreibung(v.anfrage, vok),
        "bewerten": v.anfrage.bewerten,
        "tiefe": v.anfrage.tiefe,
    }
    if v.ok:
        d = liste(daten, filter_)
        antwort["anzahl"] = d["anzahl"]
        if d["anzahl"] == 0:
            lockern = lockerungen(daten, filter_)
            antwort["vorschlag"] = lockern[0] if lockern else None
    return antwort


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

        def ausfuehren() -> None:
            try:
                a.ergebnis = arbeit(lambda m: a.meldungen.append(m))
                a.status = "fertig"
            except Exception as exc:
                a.meldungen.append(f"Fehler: {exc}")
                a.meldungen.append(traceback.format_exc(limit=3))
                a.status = "fehler"

        threading.Thread(target=ausfuehren, daemon=True).start()
        return a


# ------------------------------------------------------------------ Tiefenanalyse (Bauschritt 6)


class Analysen:
    """Eine Tiefenanalyse zur Zeit, weitere warten in `state/analysis_queue.yaml`."""

    def __init__(self, paths: Paths, starter: Any = subprocess.Popen) -> None:
        self.paths = paths
        self.starter = starter
        self.lock = threading.Lock()
        self.laufend: dict[str, Any] = {}  # ISIN -> Prozess

    @property
    def datei(self) -> Any:
        return lauf.warteschlange_datei(self.paths)

    def warteschlange(self) -> list[str]:
        return lauf.warteschlange(self.paths)

    def _aktiv(self) -> list[str]:
        return [i for i, p in self.laufend.items() if p.poll() is None]

    def starten(self, isin: str) -> dict[str, Any]:
        with self.lock:
            if isin in self._aktiv() or isin in self.warteschlange():
                return {"status": "schon_geplant"}
            if self._aktiv():
                yaml_schreiben(
                    self.datei,
                    "# Warteschlange Tiefenanalysen",
                    {"isins": [*self.warteschlange(), isin]},
                )
                return {"status": "wartet", "vor_dir": len(self.warteschlange()) - 1}
            if claude_cli.pfad() is None and self.starter is subprocess.Popen:
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
            yaml_schreiben(self.datei, "# Warteschlange Tiefenanalysen", {"isins": schlange[1:]})
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


# ------------------------------------------------------------------ Titel, Vergleich, Historie


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
            metrik_lauf = store.load_metric_run(conn, issuer)
            if metrik_lauf:
                for r in store.load_metrics(conn, issuer):
                    if r.period_end == metrik_lauf[2] and r.statistik in ("wert", "aktuell", "ttm"):
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
    checks = tr_checks.load(paths.tr_checks)
    pruefung = checks.get(isin)
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
        "tr": pruefung.status.value if pruefung else "ungeprueft",
        "verlauf": historie.notenverlauf(paths, isin),
        "tiefenanalyse": eskalationen.tiefenanalyse_ergebnisse(paths).get(isin),
        "quellensteuer": _quellensteuer(paths, info[1] if info else None),
    }


def _quellensteuer(paths: Paths, land: str | None) -> dict[str, Any] | None:
    """Quellensteuer auf Dividenden im Sitzland, nur Information (SPEC 5.2 Nr. 12)."""
    import yaml

    cfg = yaml.safe_load((paths.config / "withholding_tax.yaml").read_text("utf-8")) or {}
    eintrag = (cfg.get("laender") or {}).get(land or "")
    if not eintrag:
        return None
    return {
        **{k: str(v) for k, v in eintrag.items()},
        "quelle": str(cfg.get("quelle", "")),
        "geprueft": bool(cfg.get("geprueft")),
    }


def vergleich(paths: Paths, isins: list[str]) -> list[dict[str, Any]]:
    """Zwei bis vier Titel nebeneinander (SPEC 13.3 Vergleich): Note und Säulen, Kennzahlen der
    Note mit Perzentil, Bewertungsbedingung, Risiko."""
    out = []
    for isin in isins[:4]:
        t = titel_detail(paths, isin)
        n, det = t["note"] or {}, t["detail"] or {}
        out.append(
            {
                "isin": isin,
                "name": t["name"],
                "land": t["land"],
                "note": n.get("grade"),
                "konfidenz": n.get("konfidenz"),
                "risiko": n.get("risiko"),
                "kategorie": n.get("kategorie"),
                "score": n.get("score"),
                "branche": n.get("branche"),
                "saeulen": det.get("saeulen", {}),
                "horizonte": {
                    k: {"name": v.get("name"), "note": v.get("note")}
                    for k, v in (det.get("horizonte") or {}).items()
                },
                "kennzahlen": {
                    f"{r['kennzahl']} ({r['statistik']})": {
                        "wert": r["wert"],
                        "perzentil": r["perzentil"],
                        "saeule": r["saeule"],
                    }
                    for r in det.get("raenge", [])
                },
                "bewertungsbedingung": det.get("bewertungsbedingung"),
                "kappungen": det.get("kappungen", []),
                "risiko_stufen": det.get("risiko_stufen"),
                "grund": n.get("grund"),
            }
        )
    return out


def historie_daten(paths: Paths) -> dict[str, Any]:
    analysen = [
        {
            "run_id": z.run_id,
            "isin": z.isin,
            "status": z.status,
            "erstellt": z.erstellt,
            "bericht": f"/bericht/{z.run_id}"
            if (paths.runs / z.run_id / "report.html").exists()
            else None,
        }
        for z in sorted(orchestrator.laufende(paths), key=lambda z: z.erstellt, reverse=True)
    ]
    return {
        "laeufe": lauf.laeufe(paths),
        "analysen": analysen,
        "notenkontrolle": historie.notenkontrolle(paths),
    }


# ------------------------------------------------------------------ Server


def handler_fuer(
    paths: Paths,
    daten: Daten,
    aufgaben: Aufgaben,
    analysen: Analysen | None = None,
    modell: anfrage.Modell | bool | None = True,
) -> type[BaseHTTPRequestHandler]:
    """`modell`: Übersetzer für Freitext. True: `claude -p`, falls installiert. None oder
    False: nur die Wortliste. Sonst eine Funktion (Tests)."""
    seite = files("stockagent.dashboard").joinpath("template.html").read_text("utf-8")
    tief = analysen or Analysen(paths)
    vok = anfrage.Vokabular.laden(paths)
    uebersetzer = (
        anfrage.claude_modell(vok) if modell is True else modell if callable(modell) else None
    )
    plaene: dict[str, lauf.Plan] = {}

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
            f = self._filter()
            if pfad == "/":
                self._text(seite, "text/html; charset=utf-8")
            elif pfad == "/api/liste":
                self._json(liste(daten, f))
            elif pfad == "/api/freitext":
                self._json(freitext(f.get("text", ""), daten, vok, uebersetzer))
            elif pfad == "/api/lockern":
                self._json(lockerungen(daten, f))
            elif pfad == "/api/karte":
                self._json(karte(daten, f))
            elif pfad == "/api/vergleich":
                isins = [i.upper() for i in f.get("isins", "").split(",") if i]
                self._json(vergleich(paths, isins))
            elif pfad == "/api/aenderungen":
                seit = date.fromisoformat(f["seit"]) if f.get("seit") else None
                self._json(historie.aenderungen(paths, seit))
            elif pfad == "/api/historie":
                self._json(historie_daten(paths))
            elif pfad == "/api/methodik":
                self._json(historie.methodik(paths))
            elif pfad == "/api/ansichten":
                self._json(anfrage.ansichten(paths))
            elif pfad == "/api/status":
                self._json(
                    {
                        "claude": claude_cli.pfad() is not None,
                        "warteschlange": tief.warteschlange(),
                        "letzte_anfrage": a.model_dump()
                        if (a := lauf.letzte_anfrage(paths))
                        else None,
                    }
                )
            elif pfad.startswith("/api/titel/"):
                self._json(titel_detail(paths, pfad.rsplit("/", 1)[1].upper()))
            elif pfad.startswith("/api/aufgabe/"):
                aufgabe = aufgaben.alle.get(pfad.rsplit("/", 1)[1])
                self._json(asdict(aufgabe) if aufgabe else {"fehler": "unbekannt"})
            elif pfad.startswith("/api/analyse/"):
                self._json(tief.stand(pfad.rsplit("/", 1)[1].upper()))
            elif pfad.startswith("/bericht/"):
                run_id = pfad.rsplit("/", 1)[1]
                datei = paths.runs / run_id / "report.html"
                if RUN_ID.match(run_id) and datei.exists():
                    self._text(datei.read_text("utf-8"), "text/html; charset=utf-8")
                else:
                    self._json({"fehler": "nicht gefunden"}, HTTPStatus.NOT_FOUND)
            elif pfad.startswith("/lauf/"):
                lauf_id = pfad.rsplit("/", 1)[1]
                datei = lauf.ordner(paths, lauf_id) / "report.md"
                if LAUF_ID.match(lauf_id) and datei.exists():
                    self._text(datei.read_text("utf-8"), "text/plain; charset=utf-8")
                else:
                    self._json({"fehler": "nicht gefunden"}, HTTPStatus.NOT_FOUND)
            elif pfad == "/api/eskalationen":
                self._json([asdict(fall) for fall in eskalationen.faelle(paths)])
            elif pfad == "/api/export.csv":
                buf = io.StringIO()
                w = csv.writer(buf, delimiter=";")
                ohne = {"horizonte", "saeulen"}
                felder = [x for x in Zeile.__dataclass_fields__ if x not in ohne]
                namen = list(daten.horizont_namen)
                w.writerow([*felder, *(f"note_{h}" for h in namen)])
                for z in liste(daten, f)["zeilen"]:
                    w.writerow(
                        [
                            *(z[x] for x in felder),
                            *(z["horizonte"].get(h, {}).get("note", "") for h in namen),
                        ]
                    )
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
            elif pfad == "/api/laufplan":
                # „Alle bewerten“ oder „Auswahl bewerten“: zuerst nur der Plan (SPEC 9.6)
                filter_ = {str(k): str(v) for k, v in (body.get("filter") or {}).items() if v}
                a = anfrage.aus_filter(filter_, vok)
                a.text = str(body.get("text", ""))
                if body.get("isins"):
                    a.isins = [str(i).upper() for i in body["isins"]][:50]
                if body.get("tiefe") in vok.tiefen:
                    a.tiefe = body["tiefe"]
                a.bewerten = True
                fehler = anfrage.pruefen(a, vok)
                if fehler:
                    self._json({"fehler": "; ".join(fehler)}, HTTPStatus.BAD_REQUEST)
                    return
                plan = lauf.planen(paths, daten, a, vok)
                plaene[plan.lauf_id] = plan
                self._json(asdict(plan))
            elif pfad == "/api/lauf":
                # Erst nach Lucas Bestätigung im Dashboard (SPEC 9.6), nur ein gezeigter Plan
                plan_ = plaene.pop(str(body.get("lauf_id", "")), None)
                if plan_ is None or body.get("bestaetigt") is not True:
                    self._json({"fehler": "Laufplan unbekannt oder nicht bestätigt"}, 400)
                    return

                def lauf_arbeit(melde: Any) -> dict[str, Any]:
                    erg = lauf.ausfuehren(paths, plan_, daten, vok, tief=tief.starten, melde=melde)
                    return {
                        "lauf_id": erg.lauf_id,
                        "bericht": f"/lauf/{erg.lauf_id}",
                        "bewertet": len(erg.bewertet),
                        "fehler": len(erg.fehler),
                        "tiefenanalysen": erg.tiefenanalysen,
                    }

                self._json(asdict(aufgaben.starte("lauf", None, lauf_arbeit)))
            elif pfad == "/api/ansichten":
                try:
                    filter_ = {str(k): str(v) for k, v in (body.get("filter") or {}).items()}
                    anfrage.ansicht_speichern(paths, str(body.get("name", "")), filter_)
                except ValueError as exc:
                    self._json({"fehler": str(exc)}, HTTPStatus.BAD_REQUEST)
                    return
                self._json({"ok": True})
            elif pfad == "/api/ansichten/loeschen":
                try:
                    anfrage.ansicht_speichern(paths, str(body.get("name", "")), None)
                except ValueError as exc:
                    self._json({"fehler": str(exc)}, HTTPStatus.BAD_REQUEST)
                    return
                self._json({"ok": True})
            elif pfad.startswith("/api/analyse/"):
                self._json(tief.starten(isin))
            elif pfad.startswith("/api/stern/"):
                merk.stern(isin, bool(body.get("an")))
                daten.neu_laden()
                self._json({"ok": True})
            elif pfad.startswith("/api/notiz/"):
                merk.notiz(isin, str(body.get("text", "")))
                self._json({"ok": True})
            elif pfad.startswith("/api/entscheiden/"):
                run_id = teile[-1]
                if not RUN_ID.match(run_id):
                    self._json({"fehler": "unbekannter Lauf"}, HTTPStatus.NOT_FOUND)
                    return
                try:
                    e = eskalationen.entscheiden(
                        paths, run_id, str(body.get("entscheidung", "")), str(body.get("notiz", ""))
                    )
                except (eskalationen.EskalationFehler, orchestrator.LaufFehler) as exc:
                    self._json({"fehler": str(exc)}, HTTPStatus.BAD_REQUEST)
                    return
                self._json({"ok": True, "kategorie": e["kategorie"]})
            elif pfad.startswith("/api/tr/"):
                handelbar = bool(body.get("handelbar"))
                tr_checks.record(paths.tr_checks, isin, handelbar, datetime.now(UTC).date())
                daten.neu_laden()
                self._json({"ok": True})
            else:
                self._json({"fehler": "nicht gefunden"}, HTTPStatus.NOT_FOUND)

    return Handler


def server(
    paths: Paths,
    port: int = 8765,
    *,
    analysen: Analysen | None = None,
    modell: anfrage.Modell | bool | None = True,
) -> ThreadingHTTPServer:
    daten = Daten(paths)
    return ThreadingHTTPServer(
        ("127.0.0.1", port), handler_fuer(paths, daten, Aufgaben(), analysen, modell)
    )
