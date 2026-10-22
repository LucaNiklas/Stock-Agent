"""Lauf nach Zeitplan (Bauschritt 12, SPEC 9.1 bis 9.3, 13.4, 15.2, 16.14, ADR 0015).

`stockagent run --profile scheduled --yes` startet einen Lauf ohne Rückfragen:

1. Sperre gegen zwei gleichzeitige Läufe (`runs/_laeufe/zeitplan.lock`).
2. Universum aktualisieren (höchstens wöchentlich, die Regel steht in `universe.update`).
3. Noten der Beobachtungsliste neu rechnen (Python, keine Modellkosten), Daten werden dabei
   nachgeladen.
4. Ereignisse seit dem letzten Lauf nach Zeitplan (SPEC 9.2): neuer Bericht und Restatement bei
   Titeln der Beobachtungsliste, Insider-Cluster-Käufe bei allen bewerteten Titeln, Noten- und
   Kategoriewechsel der Beobachtungsliste. Die Titel werden markiert (`state/markierungen.yaml`).
5. Nur bei Tiefe standard oder tief im Profil: Tiefenanalyse für Ereignistitel bis zur Grenze
   (HR-18), über die Warteschlange des Dashboards oder nacheinander über `claude -p` (Abo).
6. Eskalationen als GitHub-Issues abgleichen (SPEC 16.14), Benachrichtigung (SPEC 13.4).

Der Zeitplan läuft nur, wenn Luca ihn einschaltet (`stockagent zeitplan an`, SPEC 19 Nr. 4).
Kein API-Schlüssel: die Agenten laufen weiter über das Abo.
"""

from __future__ import annotations

import contextlib
import json
import os
import plistlib
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from stockagent import anfrage as anf
from stockagent import benachrichtigung, eskalation_issues, eskalationen, historie, lauf, universe
from stockagent.data import store
from stockagent.paths import Paths
from stockagent.titelliste import Daten, Merkliste, yaml_schreiben

PROFIL = "scheduled"
LABEL_LAUNCHD = "de.stockagent.zeitplan"


class ZeitplanFehler(RuntimeError):
    pass


# ------------------------------------------------------------------ Schalter und Stand


def _state(paths: Paths) -> Path:
    return paths.root / "state" / "zeitplan.yaml"


def stand(paths: Paths) -> dict[str, Any]:
    d = _state(paths)
    return dict(yaml.safe_load(d.read_text("utf-8")) or {}) if d.exists() else {}


def _stand_schreiben(paths: Paths, daten: dict[str, Any]) -> None:
    kopf = "# Zeitplan (Bauschritt 12): Lucas Schalter und letzter Lauf"
    yaml_schreiben(_state(paths), kopf, daten)


def schalten(paths: Paths, an: bool, now: datetime | None = None) -> dict[str, Any]:
    s = stand(paths)
    s["aktiv"] = an
    s["geaendert"] = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    _stand_schreiben(paths, s)
    return s


def konfig(paths: Paths) -> dict[str, Any]:
    cfg = lauf.konfig(paths)
    return {"profil": cfg["profile"][PROFIL], **cfg["zeitplan"]}


# ------------------------------------------------------------------ Sperre


@contextlib.contextmanager
def sperre(paths: Paths):  # type: ignore[no-untyped-def]
    datei = paths.runs / "_laeufe" / "zeitplan.lock"
    datei.parent.mkdir(parents=True, exist_ok=True)
    if datei.exists():
        try:
            pid = int(datei.read_text().strip() or 0)
            os.kill(pid, 0)
        except (ValueError, ProcessLookupError, PermissionError):
            datei.unlink(missing_ok=True)  # Rest eines abgebrochenen Laufs
        else:
            raise ZeitplanFehler(f"Ein Lauf nach Zeitplan läuft schon (Prozess {pid})")
    datei.write_text(str(os.getpid()))
    try:
        yield
    finally:
        datei.unlink(missing_ok=True)


# ------------------------------------------------------------------ Ereignisse (SPEC 9.2)


@dataclass
class Ereignis:
    isin: str
    name: str
    art: str  # Neuer Bericht, Restatement, Insider-Cluster, Notenwechsel, Kategoriewechsel
    text: str
    tag: str


def ereignisse(
    paths: Paths, daten: Daten, seit: datetime, beobachtung: set[str], cluster_tage: int
) -> list[Ereignis]:
    namen = {z.isin: z.name for z in daten.zeilen}
    conn = store.connect_read(paths.db)
    try:
        isin_von = {
            str(i): str(isin)
            for i, isin in conn.execute(
                "SELECT issuer_id, isin FROM grades WHERE issuer_id IS NOT NULL"
            ).fetchall()
        }
        isin_von.update(
            dict(
                conn.execute(
                    "SELECT 'sec:' || cik, isin FROM isin_cik WHERE status = 'zugeordnet'"
                ).fetchall()
            )
        )
        berichte = store.berichte_seit(conn, seit.date())
        restatements = store.restatements_seit(conn, seit.date())
        grades = store.load_grades(conn)
    finally:
        conn.close()
    out: list[Ereignis] = []
    for issuer, tag, form in berichte:
        isin = isin_von.get(issuer)
        if isin in beobachtung and tag.replace(tzinfo=UTC) > seit:
            out.append(
                Ereignis(
                    isin,
                    namen.get(isin, isin),
                    "Neuer Bericht",
                    f"{form or 'Bericht'} veröffentlicht",
                    tag.date().isoformat(),
                )
            )
    for issuer, anzahl, tag in restatements:
        isin = isin_von.get(issuer)
        if isin in beobachtung:
            out.append(
                Ereignis(
                    isin,
                    namen.get(isin, isin),
                    "Restatement",
                    f"{anzahl} frühere Werte geändert",
                    tag.date().isoformat(),
                )
            )
    grenze = seit.date() - timedelta(days=cluster_tage)
    for g in grades:
        det = json.loads(g.detail_json or "{}")
        kaeufe = [
            x
            for x in (det.get("insider") or {}).get("geschaefte", [])
            if x.get("cluster")
            and x.get("art") == "buy"
            and date.fromisoformat(x["handelstag"]) > grenze
        ]
        if kaeufe and g.computed_at > seit:
            personen = ", ".join(sorted({str(x["person"]) for x in kaeufe}))[:200]
            out.append(
                Ereignis(
                    g.isin,
                    namen.get(g.isin, g.isin),
                    "Insider-Cluster",
                    f"Käufe am offenen Markt: {personen}",
                    max(x["handelstag"] for x in kaeufe),
                )
            )
    wechsel = historie.aenderungen(paths, seit.date())["noten"]
    for w in wechsel:
        if w["isin"] in beobachtung and w["art"] != "neu bewertet":
            text = (
                f"Note {w['note_vorher']} -> {w['note']}"
                if w["art"] == "Notenwechsel"
                else f"{w['kategorie_vorher']} -> {w['kategorie']}"
            )
            out.append(Ereignis(w["isin"], w["name"], w["art"], text, w["tag"]))
    return out


def markieren(paths: Paths, liste: list[Ereignis], lauf_id: str) -> None:
    """Ereignisse an den Titeln vermerken (`state/markierungen.yaml`), die letzten 10 je Titel."""
    datei = paths.root / "state" / "markierungen.yaml"
    alt = dict(yaml.safe_load(datei.read_text("utf-8")) or {}) if datei.exists() else {}
    for e in liste:
        eintraege = [
            {"art": e.art, "text": e.text, "tag": e.tag, "lauf": lauf_id},
            *alt.get(e.isin, []),
        ]
        alt[e.isin] = eintraege[:10]
    yaml_schreiben(datei, "# Ereignisse je Titel aus Läufen nach Zeitplan (SPEC 9.2)", alt)


def markierungen(paths: Paths) -> dict[str, list[dict[str, Any]]]:
    datei = paths.root / "state" / "markierungen.yaml"
    return dict(yaml.safe_load(datei.read_text("utf-8")) or {}) if datei.exists() else {}


# ------------------------------------------------------------------ Lauf


@dataclass
class ZeitplanErgebnis:
    lauf_id: str
    universum: str
    bewertet: int
    fehler: dict[str, str]
    ereignisse: list[dict[str, str]]
    tiefenanalysen: dict[str, dict[str, Any]]
    issues: dict[str, Any] | None
    benachrichtigung: dict[str, Any]
    hinweise: list[str] = field(default_factory=list)


@dataclass
class Lader:
    """Netz und Außenwelt, in Tests ersetzt."""

    universum: Callable[[Paths], str] = lambda p: universe.update(p).message or "aktualisiert"
    bewerten: lauf.Bewerten | None = None
    tief: Callable[[Paths, str], lauf.Tief | None] | None = None
    gh: eskalation_issues.Gh | None = None
    sender_fuer: Callable[..., Any] = benachrichtigung.sender
    env: dict[str, str] | None = None


def ausfuehren(
    paths: Paths,
    *,
    lader: Lader | None = None,
    now: datetime | None = None,
    melde: lauf.Melde = lambda _: None,
) -> ZeitplanErgebnis:
    lader = lader or Lader()
    now = now or datetime.now(UTC)
    if not stand(paths).get("aktiv"):
        raise ZeitplanFehler(
            "Zeitplan ist aus. Einschalten mit `stockagent zeitplan an` (SPEC 19 Nr. 4)."
        )
    cfg = konfig(paths)
    with sperre(paths):
        hinweise: list[str] = []
        if cfg["universum_aktualisieren"]:
            try:
                uni = lader.universum(paths)
            except Exception as exc:  # Netz: der Lauf geht mit der vorhandenen Liste weiter
                uni = f"nicht aktualisiert: {str(exc)[:200]}"
                hinweise.append(f"Universum {uni}")
        else:
            uni = "aus"
        melde(f"Universum: {uni}")

        vok = anf.Vokabular.laden(paths)
        daten = Daten(paths)
        profil = {k: v for k, v in cfg["profil"].items() if k not in ("beschreibung", "zeitplan")}
        a = anf.Anfrage(weg="profil", text=PROFIL, bewerten=True, **profil)
        plan = lauf.planen(paths, daten, a, vok, now=now)
        # Beobachtungsliste immer neu bewerten (Ereignisse brauchen frische Daten), Grenze bleibt
        beobachtung = Merkliste(paths.root).sterne()
        bewertbar = [z.isin for z in daten.zeilen if z.isin in beobachtung]
        max_b = int(lauf.konfig(paths)["grenzen"]["max_bewertungen_je_lauf"])
        plan.zu_bewerten = bewertbar[:max_b]
        plan.tief_anzahl = 0  # Tiefenanalysen nur für Ereignistitel, siehe unten
        erg = lauf.ausfuehren(
            paths, plan, daten, vok, bewerten=lader.bewerten, tief=None, melde=melde, merken=False
        )

        letzter = stand(paths).get("letzter_lauf")
        seit = datetime.fromisoformat(letzter) if letzter else None
        liste = (
            ereignisse(paths, daten, seit, beobachtung, int(cfg["insider_cluster_tage"]))
            if seit
            else []
        )
        # Schon gemeldete Ereignisse (gleiche Art und gleicher Text am Titel) nicht wiederholen
        bekannt = {
            (isin, m["art"], m["text"]) for isin, ms in markierungen(paths).items() for m in ms
        }
        liste = [e for e in liste if (e.isin, e.art, e.text) not in bekannt]
        if seit is None:
            hinweise.append("Erster Lauf nach Zeitplan: Ausgangsstand, noch keine Ereignisse.")
        markieren(paths, liste, plan.lauf_id)

        tiefen: dict[str, dict[str, Any]] = {}
        tiefe = str(cfg["profil"].get("tiefe", "schnell"))
        if tiefe != "schnell" and liste:
            grenze = int(lauf.konfig(paths)["grenzen"]["max_tiefenanalysen_je_lauf"])
            titel = list(dict.fromkeys(e.isin for e in liste))[:grenze]
            starter = (
                lader.tief(paths, cfg["tiefenanalyse"])
                if lader.tief
                else lauf.in_warteschlange(paths)
                if cfg["tiefenanalyse"] == "warteschlange"
                else lauf.tief_nacheinander(paths)
            )
            for isin in titel:
                tiefen[isin] = starter(isin) if starter else {"status": "vorgesehen"}

        issues = None
        if cfg["github_issues"]:
            try:
                gh = lader.gh or eskalation_issues.gh_cli(paths.root)
                issues = eskalation_issues.abgleichen(paths, gh)
            except Exception as exc:  # kein gh, kein Netz: steht im Bericht
                issues = {"fehler": [str(exc)[:200]]}
                hinweise.append(f"GitHub-Issues nicht abgeglichen: {str(exc)[:200]}")

        daten.neu_laden()
        attraktiv = sum(1 for z in daten.zeilen if z.kategorie == "Attraktiv")
        offen = len(eskalationen.faelle(paths))
        betreff = f"Stockagent {now:%d.%m.%Y}: {len(liste)} Ereignisse, {offen} Eskalationen"
        zeilen = [
            f"Beobachtungsliste: {len(erg.bewertet)} bewertet, {len(erg.fehler)} Fehler.",
            f"Kategorie Attraktiv (Einordnung, keine Empfehlung): {attraktiv} Titel.",
            *(f"- {e.name}: {e.art}, {e.text}" for e in liste[:15]),
            f"Offene Eskalationen: {offen}.",
            f"Dashboard: {cfg['dashboard_adresse']}",
        ]
        ordner = lauf.ordner(paths, plan.lauf_id)
        nachricht = benachrichtigung.senden(
            ordner,
            betreff,
            "\n".join(zeilen),
            list(cfg["benachrichtigung"]["kanaele"]),
            env=lader.env,
            sender_fuer=lader.sender_fuer,
        )
        ergebnis = ZeitplanErgebnis(
            lauf_id=plan.lauf_id,
            universum=uni,
            bewertet=len(erg.bewertet),
            fehler=erg.fehler,
            ereignisse=[asdict(e) for e in liste],
            tiefenanalysen=tiefen,
            issues=issues,
            benachrichtigung=nachricht,
            hinweise=hinweise,
        )
        (ordner / "zeitplan.json").write_text(
            json.dumps(asdict(ergebnis), ensure_ascii=False, indent=1, default=str), "utf-8"
        )
        with (ordner / "report.md").open("a", encoding="utf-8") as fh:
            fh.write("\n## Ereignisse seit dem letzten Lauf nach Zeitplan\n\n")
            fh.writelines(f"- {e.name} ({e.isin}): {e.art}, {e.text}, {e.tag}\n" for e in liste)
            if not liste:
                fh.write("- keine\n")
            fh.write("\n## Zeitplan\n\n")
            fh.writelines(f"- {h}\n" for h in hinweise)
            fh.write(f"- Benachrichtigung: {nachricht}\n")
            fh.write(
                "- Nicht geprüft: Ad-hoc-Mitteilungen zu Prognosesenkung und Prüferwechsel "
                "(keine strukturierte Quelle, ADR 0015).\n"
            )
        s = stand(paths)
        s["letzter_lauf"] = now.isoformat(timespec="seconds")
        s["letzter_lauf_id"] = plan.lauf_id
        _stand_schreiben(paths, s)
        return ergebnis


# ------------------------------------------------------------------ Einrichten (macOS)


def launchd_plist(paths: Paths, uhrzeit: str, uv: str | None = None) -> bytes:
    """LaunchAgent für macOS: täglich zur Uhrzeit `uv run stockagent run --profile scheduled
    --yes` im Projektordner. Läuft nur, wenn der Mac an ist (SPEC 15.2)."""
    stunde, minute = (int(x) for x in uhrzeit.split(":"))
    uv = uv or shutil.which("uv") or "uv"
    log = str(paths.runs / "_laeufe" / "zeitplan.log")
    return plistlib.dumps(
        {
            "Label": LABEL_LAUNCHD,
            "ProgramArguments": [
                uv,
                "run",
                "--directory",
                str(paths.root),
                "stockagent",
                "run",
                "--profile",
                PROFIL,
                "--yes",
            ],
            "WorkingDirectory": str(paths.root),
            "StartCalendarInterval": {"Hour": stunde, "Minute": minute},
            "StandardOutPath": log,
            "StandardErrorPath": log,
            "EnvironmentVariables": {
                "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin",
                "STOCKAGENT_HOME": str(paths.root),
            },
        }
    )


def plist_pfad() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL_LAUNCHD}.plist"
