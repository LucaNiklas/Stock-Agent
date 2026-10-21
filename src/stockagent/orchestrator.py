"""Zustandsautomat der Tiefenanalyse (SPEC 8.5, 15.1, Bauschritt 6).

Python legt den Plan fest, Claude Code führt nur aus:

1. `stockagent analyze <ISIN>` legt einen Lauf an: Recherche und Berechnung in Python (Daten,
   Kennzahlen, Note mit Vergleichsgruppe, Jahresberichte als Seitentext), Dossier und Plan.
2. `stockagent next <run_id>` nennt die fälligen Aufträge mit Eingabedatei. Unabhängige Aufträge
   derselben Abteilung kommen gemeinsam, damit sie parallel laufen.
3. Die Antwort eines Agenten nimmt `stockagent accept` an (aus dem Stop-Hook des Subagents oder
   von der Hauptsitzung). Eine Antwort für einen nicht beauftragten Auftrag wird abgelehnt
   (Reihenfolge), eine mit verletzter Schranke geht höchstens zweimal zurück, dann `escalated`.
4. Sind alle Aufträge erledigt, entstehen Entscheidung (`decision.json`, HR-13) und Bericht.

Plan je Lauf (Abhängigkeiten über Fächer, ein Fach kann nach einer Nachforderung einen zweiten
Auftrag bekommen):

    A1 je Hinweis an A1 -> A3, A4 (und A6 bei Insidergeschäften) -> A5 -> A7 -> A3E (Erwiderung)
    -> J1, J2 -> A9 -> Bericht

Jede Abteilung bekommt nur die Übergabe der vorigen als Eingabe (SPEC 8.1). Prüfer arbeiten
blind (HR-14). Konfiguration wird beim Anlegen gehasht und bei jedem Schritt verglichen (HR-11).
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from stockagent import bewertung, metrics_update
from stockagent.agents import eingaben, runner
from stockagent.data import dokumente, store
from stockagent.data.sources import sec
from stockagent.paths import Paths
from stockagent.platzhalter import Werte

ENDSTATUS = ("angenommen", "eskaliert")
ABTEILUNG = {
    "A1": "Recherche",
    "A3": "Auswertung",
    "A4": "Auswertung",
    "A5": "Auswertung",
    "A6": "Auswertung",
    "A7": "Auswertung",
    "A3E": "Auswertung",
    "J1": "Prüfung",
    "J2": "Prüfung",
    "A9": "Bericht",
}


class LaufFehler(RuntimeError):
    pass


# ------------------------------------------------------------------ Zustand


@dataclass
class Auftrag:
    id: str
    slot: str
    agent: str
    nr: int = 1
    deps: list[str] = field(default_factory=list)
    status: str = "offen"  # offen, beauftragt, angenommen, eskaliert
    versuche: int = 0
    fehler: list[str] = field(default_factory=list)
    eingabe: str = ""
    ausgabe: str = ""
    beauftragt_um: str | None = None
    fertig_um: str | None = None
    zweck: str = ""


@dataclass
class Zustand:
    run_id: str
    isin: str
    issuer_id: str
    cik: str
    name: str
    erstellt: str
    config_hash: str
    status: str = "laeuft"  # laeuft, fertig, eskaliert, abgebrochen
    grund: str | None = None
    auftraege: list[Auftrag] = field(default_factory=list)
    dokumente: list[dict[str, Any]] = field(default_factory=list)
    funde: list[dict[str, Any]] = field(default_factory=list)  # A1-Fundstellen
    grenzen: list[str] = field(default_factory=list)  # HR-16

    def auftrag(self, auftrag_id: str) -> Auftrag:
        for a in self.auftraege:
            if a.id == auftrag_id:
                return a
        raise LaufFehler(f"Auftrag {auftrag_id} gibt es in Lauf {self.run_id} nicht")

    def fach_fertig(self, slot: str) -> bool:
        im_fach = [a for a in self.auftraege if a.slot == slot]
        return bool(im_fach) and all(a.status in ENDSTATUS for a in im_fach)

    def ergebnis(self, slot: str) -> Auftrag | None:
        """Letzter angenommener Auftrag eines Fachs."""
        fertig = [a for a in self.auftraege if a.slot == slot and a.status == "angenommen"]
        return max(fertig, key=lambda a: a.nr) if fertig else None


def _ordner(paths: Paths, run_id: str) -> Path:
    return paths.runs / run_id


def laden(paths: Paths, run_id: str) -> Zustand:
    datei = _ordner(paths, run_id) / "state.json"
    if not datei.exists():
        raise LaufFehler(f"Lauf {run_id} nicht gefunden")
    data = json.loads(datei.read_text("utf-8"))
    data["auftraege"] = [Auftrag(**a) for a in data["auftraege"]]
    return Zustand(**data)


def _speichern(paths: Paths, z: Zustand) -> None:
    datei = _ordner(paths, z.run_id) / "state.json"
    tmp = datei.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(z), ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(datei)


@contextlib.contextmanager
def _gesperrt(paths: Paths, run_id: str) -> Iterator[Zustand]:
    """Zustand unter Dateisperre lesen und schreiben (parallele Annahmen aus Hooks)."""
    ordner = _ordner(paths, run_id)
    if not ordner.exists():
        raise LaufFehler(f"Lauf {run_id} nicht gefunden")
    with (ordner / ".lock").open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        z = laden(paths, run_id)
        yield z
        _speichern(paths, z)


def _jetzt(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).isoformat(timespec="seconds")


def _log(paths: Paths, run_id: str, eintrag: dict[str, Any]) -> None:
    with (_ordner(paths, run_id) / "log.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"zeit": _jetzt(), **eintrag}, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------ Konfiguration


def config_hash(paths: Paths) -> str:
    """Hash über alle Dateien in config/ und agents_src/ (HR-11)."""
    h = hashlib.sha256()
    for ordner in (paths.config, paths.root / "agents_src"):
        for f in sorted(ordner.glob("*")):
            if f.is_file():
                h.update(f.name.encode())
                h.update(f.read_bytes())
    return f"sha256:{h.hexdigest()}"


def modelle(paths: Paths) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((paths.config / "models.yaml").read_text("utf-8"))
    return data


# ------------------------------------------------------------------ Lader


def _sec_dokumente(paths: Paths, cik: str, anzahl: int) -> list[dokumente.Geladen]:
    cfg = yaml.safe_load((paths.config / "sources.yaml").read_text("utf-8"))
    client = sec.SecClient(cfg["sec"], sec.user_agent(paths.root), paths.raw)
    subs, _ = client.submissions(cik)
    conn = store.connect(paths.db)
    try:
        return [
            dokumente.lade_sec(conn, client, cik, f)
            for f in dokumente.jahresberichte(subs, datetime.now(UTC), anzahl)
        ]
    finally:
        conn.close()


@dataclass
class AnalyseLader:
    """Netzabrufe der Recherche. In Tests durch Attrappen ersetzt."""

    bewerten: Callable[[Paths, str], bewertung.Bewertung] = lambda p, i: bewertung.bewerten(p, i)
    dokumente: Callable[[Paths, str, int], list[dokumente.Geladen]] = _sec_dokumente
    # Dokumente, die A1 gefunden hat (nur HTML, nur erlaubte Domains): URL -> Seiten
    abruf: Callable[[Paths, str], list[str] | None] = lambda p, url: None


# ------------------------------------------------------------------ Anlegen


def laufende(paths: Paths) -> list[Zustand]:
    if not paths.runs.exists():
        return []
    out = []
    for f in sorted(paths.runs.glob("*/state.json")):
        with contextlib.suppress(LaufFehler, ValueError, TypeError):
            out.append(laden(paths, f.parent.name))
    return out


def _seiten_exportieren(
    paths: Paths, run_id: str, geladen: list[dokumente.Geladen]
) -> list[dict[str, Any]]:
    """Seitentext als Dateien unter runs/<run_id>/dokumente/, damit Agenten mit Read und Grep
    arbeiten können, ohne Datenbankzugriff."""
    out = []
    conn = store.connect_read(paths.db)
    try:
        for g in geladen:
            row = conn.execute(
                "SELECT period_end FROM documents WHERE doc_id = ?", [g.doc_id]
            ).fetchone()
            periode = row[0].isoformat() if row and row[0] else "ohne_periode"
            ordner = f"dokumente/{g.doc_type}_{periode}_{g.doc_hash.removeprefix('sha256:')[:12]}"
            ziel = _ordner(paths, run_id) / ordner
            ziel.mkdir(parents=True, exist_ok=True)
            inhalt = []
            for seite in range(1, g.seiten + 1):
                text = store.page_text(conn, g.doc_hash, seite) or ""
                (ziel / f"seite_{seite:03d}.txt").write_text(text, "utf-8")
                inhalt.append(" ".join(text.split())[:90])
            out.append(
                {
                    "doc_hash": g.doc_hash,
                    "doc_id": g.doc_id,
                    "doc_type": g.doc_type,
                    "periode": periode,
                    "seiten": g.seiten,
                    "ordner": f"runs/{run_id}/{ordner}",
                    "inhalt": inhalt,
                }
            )
    finally:
        conn.close()
    return out


def anlegen(
    paths: Paths,
    isin: str,
    *,
    lader: AnalyseLader | None = None,
    now: datetime | None = None,
    progress: Callable[[str], None] = lambda _: None,
) -> Zustand:
    """Lauf anlegen: Recherche und Berechnung in Python, dann Plan der Agentenaufträge."""
    now = now or datetime.now(UTC)
    lader = lader or AnalyseLader()
    isin = isin.upper()
    cfg = modelle(paths)
    aufwand = cfg["aufwand"]
    aktiv = [z for z in laufende(paths) if z.status == "laeuft"]
    if len(aktiv) >= int(aufwand["max_tiefenanalysen_gleichzeitig"]):
        raise LaufFehler(
            f"Schon {len(aktiv)} Tiefenanalysen offen (Grenze HR-18): "
            + ", ".join(z.run_id for z in aktiv)
        )

    progress(f"{isin}: Daten, Kennzahlen und Note mit Vergleichsgruppe")
    note = lader.bewerten(paths, isin)
    conn = store.connect(paths.db)
    try:
        issuer = metrics_update.issuer_for_isin(conn, isin)
        name_row = conn.execute("SELECT name FROM listings WHERE isin = ?", [isin]).fetchone()
    finally:
        conn.close()
    if issuer is None:
        raise LaufFehler(f"{isin}: kein SEC-Melder, Tiefenanalyse für Europa ab Bauschritt 7")
    cik = issuer.removeprefix("sec:")

    progress(f"{isin}: Jahresberichte als Seitentext")
    geladen = lader.dokumente(paths, cik, int(aufwand["berichte_anzahl"]))

    run_id = f"{now:%Y-%m-%dT%H-%M-%SZ}_{isin}"
    ordner = _ordner(paths, run_id)
    for sub in ("eingaben", "ausgaben", "antworten"):
        (ordner / sub).mkdir(parents=True, exist_ok=True)
    z = Zustand(
        run_id=run_id,
        isin=isin,
        issuer_id=issuer,
        cik=cik,
        name=str(name_row[0]) if name_row else isin,
        erstellt=_jetzt(now),
        config_hash=config_hash(paths),
    )
    z.dokumente = _seiten_exportieren(paths, run_id, geladen)
    if not geladen:
        z.grenzen.append("Kein Jahresbericht als Text geladen, qualitative Analyse ohne Belege")
    if note.note == "N":
        z.grenzen.append(f"Note: Status N ({note.grund})")

    conn = store.connect_read(paths.db)
    try:
        hinweise_a1 = [h for h in store.load_hinweise(conn, issuer) if h.an_agent == "A1"]
    finally:
        conn.close()
    a1 = [f"A1_h{i}" for i, _ in enumerate(hinweise_a1[:2], start=1)]
    # A6 nur, wenn es Geschäfte am offenen Markt in den letzten 24 Monaten gibt (SPEC 8.3)
    a6 = ["A6"] if eingaben.insider_meldungen(paths, z) else []
    plan = [Auftrag(x, x, "A1", zweck=hinweise_a1[i].detail) for i, x in enumerate(a1)]
    plan += [
        Auftrag("A3", "A3", "A3", deps=a1),
        Auftrag("A4", "A4", "A4", deps=a1),
        Auftrag("A5", "A5", "A5", deps=["A3", "A4"]),
        *[Auftrag("A6", "A6", "A6", deps=a1) for _ in a6],
        Auftrag("A7", "A7", "A7", deps=["A5", *a6]),
        Auftrag("A3E", "A3E", "A3E", deps=["A7"]),
        Auftrag("J1", "J1", "J1", deps=["A3E"]),
        Auftrag("J2", "J2", "J2", deps=["A3E"]),
        Auftrag("A9", "A9", "A9", deps=["J1", "J2"]),
    ]
    for a in plan:
        a.eingabe = f"runs/{run_id}/eingaben/{a.id}.json"
        a.ausgabe = f"runs/{run_id}/ausgaben/{a.id}.json"
    z.auftraege = plan
    _speichern(paths, z)
    (ordner / "dossier.json").write_text(
        json.dumps(eingaben.dossier(paths, z), ensure_ascii=False, indent=2, default=str), "utf-8"
    )
    _log(paths, run_id, {"ereignis": "angelegt", "isin": isin, "note": note.note})
    return z


# ------------------------------------------------------------------ Nächster Schritt


def _abbrechen(paths: Paths, z: Zustand, grund: str) -> None:
    z.status = "abgebrochen"
    z.grund = grund
    z.grenzen.append(f"Lauf abgebrochen: {grund}")
    _log(paths, z.run_id, {"ereignis": "abgebrochen", "grund": grund})


def _pruefe_grenzen(paths: Paths, z: Zustand, now: datetime) -> None:
    if z.status != "laeuft":
        return
    if config_hash(paths) != z.config_hash:
        _abbrechen(paths, z, "Konfiguration während des Laufs geändert (HR-11)")
        return
    minuten = int(modelle(paths)["aufwand"]["zeitlimit_minuten"])
    alter = now - datetime.fromisoformat(z.erstellt)
    if alter > timedelta(minutes=minuten):
        _abbrechen(paths, z, f"Zeitlimit von {minuten} Minuten überschritten (SPEC 8.6)")


def naechste(
    paths: Paths,
    run_id: str,
    *,
    lader: AnalyseLader | None = None,
    now: datetime | None = None,
) -> list[Auftrag]:
    """Fällige Aufträge beauftragen und alle laufenden nennen. Leer, wenn der Lauf zu Ende ist."""
    now = now or datetime.now(UTC)
    lader = lader or AnalyseLader()
    with _gesperrt(paths, run_id) as z:
        _pruefe_grenzen(paths, z, now)
        if z.status != "laeuft":
            return []
        max_parallel = int(modelle(paths)["aufwand"]["max_parallel"])
        for a in z.auftraege:
            laufend = sum(1 for x in z.auftraege if x.status == "beauftragt")
            if a.status != "offen" or laufend >= max_parallel:
                continue
            if not all(z.fach_fertig(d) for d in a.deps):
                continue
            if a.nr > 1:
                _funde_laden(paths, z, a, lader)
            daten = eingaben.bauen(paths, z, a)
            ziel = paths.root / a.eingabe
            ziel.write_text(json.dumps(daten, ensure_ascii=False, indent=2, default=str), "utf-8")
            a.status = "beauftragt"
            a.beauftragt_um = _jetzt(now)
            _log(paths, run_id, {"ereignis": "beauftragt", "auftrag": a.id, "agent": a.agent})
        offen = [a for a in z.auftraege if a.status in ("offen", "beauftragt")]
        if not offen:
            _abschliessen(paths, z, now)
            return []
        return [a for a in z.auftraege if a.status == "beauftragt"]


def _funde_laden(paths: Paths, z: Zustand, a: Auftrag, lader: AnalyseLader) -> None:
    """Vor dem zweiten Auftrag eines Fachs: Fundstellen der Nachforderung laden."""
    neu: list[dokumente.Geladen] = []
    offen = [f for f in z.funde if f.get("fuer") == a.slot and not f.get("geladen")]
    for f in offen:
        f["geladen"] = True
        seiten = lader.abruf(paths, f["url"])
        if not seiten:
            z.grenzen.append(f"Fundstelle von A1 nicht geladen: {f['url']}")
            continue
        doc_hash = "sha256:" + hashlib.sha256("\n\f".join(seiten).encode()).hexdigest()
        doc_id = f"a1:{f['url']}"
        conn = store.connect(paths.db)
        try:
            store.save_document(
                conn,
                store.DocumentRow(
                    doc_id=doc_id,
                    issuer_id=z.issuer_id,
                    doc_type=f["dokumenttyp"],
                    period_end=None,
                    published_at=datetime.now(UTC),
                    retrieved_at=datetime.now(UTC),
                    source_url=f["url"],
                    doc_hash=doc_hash,
                ),
                seiten,
                None,
            )
        finally:
            conn.close()
        neu.append(dokumente.Geladen(doc_id, doc_hash, f["dokumenttyp"], len(seiten)))
    if neu:
        z.dokumente.extend(_seiten_exportieren(paths, z.run_id, neu))


# ------------------------------------------------------------------ Annahme


@dataclass
class Annahme:
    auftrag: str
    angenommen: bool
    eskaliert: bool
    meldung: str


def annehmen(
    paths: Paths,
    run_id: str,
    text: str,
    auftrag_id: str | None = None,
    *,
    now: datetime | None = None,
) -> Annahme:
    """Antwort eines Agenten prüfen und annehmen oder mit Fehlermeldung zurückgeben."""
    now = now or datetime.now(UTC)
    if auftrag_id is None:
        kennung = runner.auftrag_aus_text(text)
        if not kennung or "/" not in kennung:
            raise LaufFehler("Antwort ohne Feld auftrag")
        auftrag_id = kennung.rsplit("/", 1)[1]
    cfg = modelle(paths)
    with _gesperrt(paths, run_id) as z:
        a = z.auftrag(auftrag_id)
        nr = sum(1 for _ in (paths.runs / run_id / "antworten").glob(f"{a.id}_*.txt")) + 1
        (paths.runs / run_id / "antworten" / f"{a.id}_{nr}.txt").write_text(text, "utf-8")
        if z.status != "laeuft":
            return Annahme(a.id, False, False, f"Lauf ist {z.status}, keine Annahme mehr")
        if a.status == "angenommen":
            return Annahme(a.id, True, False, f"Auftrag {a.id} ist schon angenommen")
        if a.status != "beauftragt":
            meldung = (
                f"Auftrag {a.id} ist {a.status}, nicht beauftragt: Schritt außerhalb der "
                "Reihenfolge abgelehnt (SPEC 15.1)"
            )
            _log(paths, run_id, {"ereignis": "reihenfolge", "auftrag": a.id})
            return Annahme(a.id, False, False, meldung)
        if config_hash(paths) != z.config_hash:
            _abbrechen(paths, z, "Konfiguration während des Laufs geändert (HR-11)")
            return Annahme(a.id, False, False, z.grund or "")

        conn = store.connect_read(paths.db)
        try:
            werte = Werte.laden(conn, z.issuer_id, _metrics_cfg(paths))
            p = runner.pruefe(
                text,
                a.agent,
                f"{run_id}/{a.id}",
                werte,
                lambda h, s: store.page_text(conn, h, s),
                eingaben.zusatzpruefung(paths, z, a),
            )
        finally:
            conn.close()
        a.versuche += 1
        erlaubt = int(cfg["aufwand"]["max_wiederholungen"])
        dauer = (now - datetime.fromisoformat(a.beauftragt_um or z.erstellt)).total_seconds()
        if p.ok or (p.antwort is not None and not p.hart and a.versuche > erlaubt):
            _ausgabe_schreiben(paths, z, a, p, cfg, now)
            a.status, a.fertig_um, a.fehler = "angenommen", _jetzt(now), [*p.weich]
            _nach_annahme(z, a, p, cfg)
            _log(
                paths,
                run_id,
                {
                    "ereignis": "angenommen",
                    "auftrag": a.id,
                    "versuch": a.versuche,
                    "sekunden": int(dauer),
                    "entfernt": len(p.entfernt),
                    "abgelehnt": len(p.abgelehnt),
                },
            )
            return Annahme(a.id, True, False, f"Auftrag {a.id} angenommen")
        a.fehler = [*p.hart, *p.weich]
        if a.versuche > erlaubt:
            a.status, a.fertig_um = "eskaliert", _jetzt(now)
            z.grenzen.append(f"Auftrag {a.id} eskaliert nach {a.versuche} Versuchen")
            _log(paths, run_id, {"ereignis": "eskaliert", "auftrag": a.id, "fehler": a.fehler})
            return Annahme(a.id, False, True, f"Auftrag {a.id} eskaliert: {a.fehler[:3]}")
        _log(paths, run_id, {"ereignis": "abgelehnt", "auftrag": a.id, "fehler": a.fehler[:10]})
        return Annahme(a.id, False, False, runner.meldung(p, a.versuche, erlaubt + 1 - a.versuche))


def _metrics_cfg(paths: Paths) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((paths.config / "metrics.yaml").read_text("utf-8"))
    return data


def _prompt(paths: Paths, vorlage: str) -> tuple[str, str]:
    """Version und Hash der gerenderten Agent-Datei (SPEC 8.4 Umschlag)."""
    datei = paths.root / ".claude" / "agents" / f"{vorlage}.md"
    versionen = yaml.safe_load(
        (paths.root / "src" / "stockagent" / "agents" / "prompts" / "versions.yaml").read_text(
            "utf-8"
        )
    )
    version = str(versionen.get(vorlage, "0"))
    if not datei.exists():
        return version, "sha256:nicht_gerendert"
    return version, "sha256:" + hashlib.sha256(datei.read_bytes()).hexdigest()


def _ausgabe_schreiben(
    paths: Paths, z: Zustand, a: Auftrag, p: runner.Pruefung, cfg: dict[str, Any], now: datetime
) -> None:
    from stockagent.agents.render import resolve_model

    agent_cfg = cfg["tiefenanalyse"]["agenten"][a.agent]
    klasse = str(cfg["agenten"][agent_cfg["modell_von"]])
    version, prompt_hash = _prompt(paths, agent_cfg["vorlage"])
    umschlag = {
        "run_id": z.run_id,
        "agent_id": agent_cfg["modell_von"] if a.agent != "A3E" else "A3_erwiderung",
        "agent_version": version,
        "prompt_hash": prompt_hash,
        "model_class": klasse if klasse != "extern" else "standard",
        "model": resolve_model(klasse, cfg),
        "lei": None,
        "input_refs": [a.eingabe],
        "created_at": now.isoformat(),
        "status": "checked",
    }
    antwort = runner.bereinigt(p)
    daten = {
        "envelope": umschlag,
        "antwort": runner.als_dict(antwort),
        "removed_claims": [runner.als_dict(r) for r in p.entfernt],
        "abgelehnt": p.abgelehnt,
        "versuche": a.versuche,
    }
    (paths.root / a.ausgabe).write_text(json.dumps(daten, ensure_ascii=False, indent=2), "utf-8")


def _nach_annahme(z: Zustand, a: Auftrag, p: runner.Pruefung, cfg: dict[str, Any]) -> None:
    """Nachforderungen (SPEC 8.5): Auftrag an A1, danach zweiter Auftrag desselben Fachs."""
    assert p.antwort is not None
    aufwand = cfg["aufwand"]
    if a.agent == "A1":
        for d in getattr(p.antwort, "dokumente", []):
            z.funde.append(
                {
                    "url": d.url,
                    "dokumenttyp": d.dokumenttyp,
                    "periode": d.periode,
                    "fuer": a.slot.removeprefix("A1_nf_"),
                }
            )
        return
    forderungen = getattr(p.antwort, "nachforderungen", [])
    if not forderungen or a.nr > int(aufwand["nachforderung_runden"]):
        return
    if len(z.auftraege) + 2 > int(aufwand["max_auftraege_je_lauf"]):
        z.grenzen.append(f"Nachforderung von {a.id} nicht bearbeitet: Auftragsgrenze (HR-18)")
        return
    a1 = Auftrag(
        f"A1_nf_{a.slot}",
        f"A1_nf_{a.slot}",
        "A1",
        zweck="; ".join(f"{n.dokumenttyp} {n.periode}: {n.grund}" for n in forderungen),
    )
    zweit = Auftrag(f"{a.slot}_2", a.slot, a.agent, nr=a.nr + 1, deps=[a1.slot])
    for neu in (a1, zweit):
        neu.eingabe = f"runs/{z.run_id}/eingaben/{neu.id}.json"
        neu.ausgabe = f"runs/{z.run_id}/ausgaben/{neu.id}.json"
    index = z.auftraege.index(a) + 1
    z.auftraege[index:index] = [a1, zweit]


# ------------------------------------------------------------------ Abschluss


def _abschliessen(paths: Paths, z: Zustand, now: datetime) -> None:
    from stockagent.judges import final_check
    from stockagent.report import analyse as bericht

    entscheidung = eingaben.entscheidung(paths, z)
    ordner = _ordner(paths, z.run_id)
    md, html = bericht.erzeugen(paths, z, entscheidung)
    # J4 Endkontrolle (SPEC 11.2 Ebene 4): Befunde eskalieren den Lauf, der Bericht bleibt zur
    # Durchsicht erhalten
    befunde = final_check.pruefen(md, entscheidung, bericht.kontext(paths, z, entscheidung))
    entscheidung["j4"] = [{"pruefung": b.pruefung, "text": b.text} for b in befunde]
    if befunde:
        entscheidung["eskalationen"].extend(f"J4 {b.pruefung}: {b.text}" for b in befunde)
    (ordner / "decision.json").write_text(
        json.dumps(entscheidung, ensure_ascii=False, indent=2, default=str), "utf-8"
    )
    (ordner / "report.md").write_text(md, "utf-8")
    (ordner / "report.html").write_text(html, "utf-8")
    z.status = "eskaliert" if entscheidung["eskalationen"] else "fertig"
    _log(paths, z.run_id, {"ereignis": "abgeschlossen", "status": z.status})


def fortschritt(z: Zustand) -> dict[str, Any]:
    """Stand je Abteilung für Anzeige und Dashboard."""
    je: dict[str, dict[str, int]] = {}
    for a in z.auftraege:
        abt = ABTEILUNG.get(a.agent, a.agent)
        je.setdefault(abt, {}).setdefault(a.status, 0)
        je[abt][a.status] += 1
    return {"run_id": z.run_id, "status": z.status, "grund": z.grund, "abteilungen": je}
