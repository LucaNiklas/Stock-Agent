"""Lauf über eine Trefferliste mit Laufplan (SPEC 9.3, 9.6, 9.7, 13.2, ADR 0014).

Ablauf: Anfrage -> Laufplan (Anzahl, Dauer, Grenze HR-18) -> Bestätigung -> Noten für alle Treffer
ohne Sprachmodell -> Tiefenanalyse für die besten Treffer bis zur Grenze -> Laufübersicht.

Ablage je Lauf unter `runs/_laeufe/<lauf_id>/`: `request.json` (Anfrage), `plan.json`,
`ergebnis.json` und `report.md`. Die Anfrage steht zusätzlich als Vorschlag für den nächsten
Start in `state/last_request.yaml`. Die Tiefenanalysen selbst haben ihre eigenen Läufe unter
`runs/<run_id>/` (Bauschritt 6).
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from stockagent import anfrage as anf
from stockagent import bewertung, claude_cli, historie
from stockagent.core.laufplan import dauer_minuten
from stockagent.paths import Paths
from stockagent.titelliste import (
    NACH_BEWERTUNG,
    OHNE_DATEN,
    Daten,
    Merkliste,
    Zeile,
    treffer,
    wert,
    yaml_schreiben,
)

NOTEN = ("A", "B", "C", "D", "E")
HINWEIS = (
    "Recherche-Grundlage, keine Anlageberatung. „Attraktiv“ ist eine Einordnung, keine Empfehlung."
)

Melde = Callable[[str], None]
Bewerten = Callable[[Paths, str], Any]
Tief = Callable[[str], dict[str, Any]]


def konfig(paths: Paths) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((paths.config / "run_profiles.yaml").read_text("utf-8"))
    return data


def ordner(paths: Paths, lauf_id: str) -> Path:
    return paths.runs / "_laeufe" / lauf_id


# ------------------------------------------------------------------ Laufplan


@dataclass
class Plan:
    lauf_id: str
    erstellt: str
    anfrage: dict[str, Any]
    beschreibung: list[tuple[str, str]]
    auswahl: int  # Titel der Auswahl (Filter, die vor dem Bewerten feststehen)
    aktuell_bewertet: int  # davon mit aktueller Note
    zu_bewerten: list[str]  # bis zur Grenze max_bewertungen_je_lauf
    zu_bewerten_gesamt: int
    nicht_bewertbar: int  # ohne SEC-, ESEF-Daten und ohne LEI
    tief_vorgesehen: int  # laut Tiefe
    tief_grenze: int  # HR-18
    tief_anzahl: int
    tief_vorschau: list[str]  # beste der schon bewerteten Treffer (vor dem Lauf)
    beobachtungsliste: list[str]
    dauer_minuten: str | None
    claude: bool
    hinweise: list[str] = field(default_factory=list)


def _veraltet(z: Zeile, grenze: date) -> bool:
    return not z.bewertet_am or date.fromisoformat(z.bewertet_am) < grenze


def auswahl_tief(
    zeilen: list[Zeile], konfidenzen: list[str], anzahl: int, zuerst: list[str]
) -> list[str]:
    """Beste Treffer nach Note, dann Konfidenz, dann Gesamtwert, nur K1 bis K3 (SPEC 9.7).
    Titel der Beobachtungsliste zuerst, wenn Luca das gewählt hat. Höchstens `anzahl`."""
    gut = [z for z in zeilen if z.note in NOTEN and z.konfidenz in konfidenzen]
    gut.sort(key=lambda z: (z.note, z.konfidenz, -wert(z)))
    reihe = list(dict.fromkeys([*zuerst, *(z.isin for z in gut)]))
    return reihe[:anzahl]


def planen(
    paths: Paths,
    daten: Daten,
    a: anf.Anfrage,
    vok: anf.Vokabular,
    *,
    now: datetime | None = None,
) -> Plan:
    now = now or datetime.now(UTC)
    cfg = konfig(paths)
    sc = yaml.safe_load((paths.config / "scoring.yaml").read_text("utf-8"))
    f = anf.als_filter(a, vok)
    auswahl = treffer(daten, f, ohne=NACH_BEWERTUNG)
    grenze_datum = now.date() - timedelta(days=int(sc["vergleichsgruppe"]["erneuern_tage"]))
    bewertbar = [z for z in auswahl if z.datenlage != OHNE_DATEN or z.lei]
    offen = [z.isin for z in bewertbar if _veraltet(z, grenze_datum)]
    max_b = int(cfg["grenzen"]["max_bewertungen_je_lauf"])
    vorgesehen = int(cfg["tiefe"][a.tiefe]["tiefenanalysen"])
    grenze = int(cfg["grenzen"]["max_tiefenanalysen_je_lauf"])
    sterne = sorted(Merkliste(paths.root).sterne()) if a.beobachtungsliste != "nein" else []
    # Nicht mehr Tiefenanalysen als mögliche Titel (Auswahl und Beobachtungsliste)
    moeglich = len({*(z.isin for z in auswahl), *sterne})
    anzahl = min(vorgesehen, grenze, moeglich)
    vorschau = auswahl_tief(
        treffer(daten, f), list(cfg["grenzen"]["tiefenanalyse_konfidenz"]), anzahl, sterne
    )
    s = cfg["schaetzung"]
    dauer = dauer_minuten(
        min(len(offen), max_b),
        anzahl,
        Decimal(str(s["minuten_je_bewertung"])),
        Decimal(str(s["minuten_je_tiefenanalyse"])),
    )
    claude = claude_cli.pfad() is not None
    hinweise = []
    if any(f.get(k) for k in NACH_BEWERTUNG):
        hinweise.append(
            "Note, Kategorie, Stil und Größe stehen erst nach dem Bewerten fest. Bewertet wird die "
            "ganze Auswahl, die Rangliste filtert danach."
        )
    if len(offen) > max_b:
        hinweise.append(
            f"Nur die ersten {max_b} von {len(offen)} Titeln werden bewertet "
            "(Grenze max_bewertungen_je_lauf in config/run_profiles.yaml). Filter enger stellen."
        )
    if vorgesehen > grenze:
        hinweise.append(
            f"Die Tiefe sieht {vorgesehen} Tiefenanalysen vor, die Grenze je Lauf ist {grenze} "
            "(HR-18). Die übrigen Treffer erscheinen mit Note in der Laufübersicht."
        )
    if anzahl:
        hinweise.append(str(s["abo_hinweis"]))
        if not claude:
            hinweise.append(
                "Claude Code (claude) ist auf diesem Rechner nicht gefunden. Tiefenanalysen können "
                "nicht starten, der Lauf rechnet nur die Noten."
            )
    ohne_daten = sum(1 for z in auswahl if z not in bewertbar)
    if ohne_daten:
        hinweise.append(
            f"{ohne_daten} Titel ohne strukturierte Abschlussdaten (weder SEC noch LEI für ESEF) "
            "werden übersprungen."
        )
    return Plan(
        lauf_id=f"{now:%Y-%m-%dT%H-%M-%SZ}_lauf",
        erstellt=now.isoformat(timespec="seconds"),
        anfrage=a.model_dump(),
        beschreibung=anf.beschreibung(a, vok),
        auswahl=len(auswahl),
        aktuell_bewertet=sum(1 for z in auswahl if z.note and not _veraltet(z, grenze_datum)),
        zu_bewerten=offen[:max_b],
        zu_bewerten_gesamt=len(offen),
        nicht_bewertbar=ohne_daten,
        tief_vorgesehen=vorgesehen,
        tief_grenze=grenze,
        tief_anzahl=anzahl,
        tief_vorschau=vorschau,
        beobachtungsliste=sterne,
        dauer_minuten=str(dauer.wert.quantize(Decimal("1"))) if dauer.wert is not None else None,
        claude=claude,
        hinweise=hinweise,
    )


# ------------------------------------------------------------------ Tiefenanalyse starten


def tief_nacheinander(paths: Paths) -> Tief:
    """Tiefenanalyse über `claude -p`, eine nach der anderen, wartet auf jede (Terminal)."""

    def start(isin: str) -> dict[str, Any]:
        if claude_cli.pfad() is None:
            return {"status": "fehler", "grund": "Claude Code (claude) nicht gefunden"}
        log = paths.runs / "_dashboard"
        log.mkdir(parents=True, exist_ok=True)
        with (log / f"{isin}.jsonl").open("ab") as fh:
            rc = subprocess.run(
                claude_cli.analyse_befehl(isin),
                cwd=paths.root,
                stdout=fh,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                check=False,
            ).returncode
        return {"status": "fertig" if rc == 0 else "fehler", "rueckgabe": rc}

    return start


def warteschlange_datei(paths: Paths) -> Path:
    return paths.root / "state" / "analysis_queue.yaml"


def warteschlange(paths: Paths) -> list[str]:
    d = warteschlange_datei(paths)
    if not d.exists():
        return []
    return [str(x) for x in (yaml.safe_load(d.read_text("utf-8")) or {}).get("isins", [])]


def in_warteschlange(paths: Paths) -> Tief:
    """Tiefenanalyse in `state/analysis_queue.yaml` einreihen. Das Dashboard arbeitet sie ab."""

    def start(isin: str) -> dict[str, Any]:
        schlange = warteschlange(paths)
        if isin not in schlange:
            yaml_schreiben(
                warteschlange_datei(paths),
                "# Warteschlange Tiefenanalysen",
                {"isins": [*schlange, isin]},
            )
        return {"status": "wartet"}

    return start


# ------------------------------------------------------------------ Ausführen


@dataclass
class Ergebnis:
    lauf_id: str
    ordner: str
    bewertet: list[str]
    fehler: dict[str, str]
    rangliste: list[dict[str, Any]]
    tiefenanalysen: dict[str, dict[str, Any]]
    grenzen: list[str]


def ausfuehren(
    paths: Paths,
    plan: Plan,
    daten: Daten,
    vok: anf.Vokabular,
    *,
    bewerten: Bewerten | None = None,
    tief: Tief | None = None,
    melde: Melde = lambda _: None,
    merken: bool = True,
) -> Ergebnis:
    """Lauf nach Lucas Bestätigung. `tief = None`: Tiefenanalysen nur auflisten (etwa für den
    Skill `/stockagent`, der sie selbst über `/analyze-stock` ausführt)."""
    bewerten = bewerten or (lambda p, i: bewertung.bewerten(p, i))
    a = anf.Anfrage(**plan.anfrage)
    ziel = ordner(paths, plan.lauf_id)
    ziel.mkdir(parents=True, exist_ok=True)
    (ziel / "request.json").write_text(a.model_dump_json(indent=2), "utf-8")
    (ziel / "plan.json").write_text(json.dumps(asdict(plan), ensure_ascii=False, indent=2), "utf-8")
    if merken:  # Läufe nach Zeitplan überschreiben Lucas letzte Anfrage nicht
        letzte_anfrage_speichern(paths, a)

    fertig, fehler = [], {}
    for nr, isin in enumerate(plan.zu_bewerten, start=1):
        melde(f"Bewerten {nr} von {len(plan.zu_bewerten)}: {isin}")
        try:
            bewerten(paths, isin)
            fertig.append(isin)
        except Exception as exc:  # ein Titel bricht den Lauf nicht ab, steht unter Grenzen
            fehler[isin] = str(exc)[:300]
    daten.neu_laden()

    cfg = konfig(paths)
    rang = treffer(daten, anf.als_filter(a, vok))
    rang.sort(key=lambda z: (z.note not in NOTEN, z.note, z.konfidenz, -wert(z)))
    tief_liste = auswahl_tief(
        rang,
        list(cfg["grenzen"]["tiefenanalyse_konfidenz"]),
        plan.tief_anzahl,
        plan.beobachtungsliste,
    )
    tiefen: dict[str, dict[str, Any]] = {}
    for isin in tief_liste:
        if tief is None:
            tiefen[isin] = {"status": "vorgesehen"}
            continue
        melde(f"Tiefenanalyse {isin}")
        try:
            tiefen[isin] = tief(isin)
        except Exception as exc:
            tiefen[isin] = {"status": "fehler", "grund": str(exc)[:300]}

    grenzen = list(plan.hinweise)
    if fehler:
        grenzen.append(f"{len(fehler)} Titel konnten nicht bewertet werden (Gründe unten).")
    if plan.nicht_bewertbar:
        grenzen.append(f"{plan.nicht_bewertbar} Titel ohne strukturierte Daten übersprungen.")
    erg = Ergebnis(
        lauf_id=plan.lauf_id,
        ordner=str(ziel.relative_to(paths.root)),
        bewertet=fertig,
        fehler=fehler,
        rangliste=[asdict(z) for z in rang],
        tiefenanalysen=tiefen,
        grenzen=grenzen,
    )
    (ziel / "ergebnis.json").write_text(
        json.dumps(asdict(erg), ensure_ascii=False, indent=1, default=str), "utf-8"
    )
    (ziel / "report.md").write_text(laufbericht(paths, plan, erg, daten), "utf-8")
    return erg


def letzte_anfrage_speichern(paths: Paths, a: anf.Anfrage) -> None:
    yaml_schreiben(
        paths.root / "state" / "last_request.yaml",
        "# Letzte Anfrage, Vorschlag für den nächsten Start (SPEC 9.7)",
        a.model_dump(),
    )


def letzte_anfrage(paths: Paths) -> anf.Anfrage | None:
    d = paths.root / "state" / "last_request.yaml"
    if not d.exists():
        return None
    try:
        return anf.Anfrage(**(yaml.safe_load(d.read_text("utf-8")) or {}))
    except ValueError:
        return None


# ------------------------------------------------------------------ Laufübersicht


def _zelle(text: Any) -> str:
    return str(text or "–").replace("|", "/")


def laufbericht(paths: Paths, plan: Plan, erg: Ergebnis, daten: Daten) -> str:
    """Laufübersicht `report.md` nach SPEC 13.2 (Teile 1 bis 3, 6 und 8)."""
    rang = erg.rangliste
    noten = Counter(z["note"] or "ohne" for z in rang)
    attraktiv = sum(1 for z in rang if z["kategorie"] == "Attraktiv")
    zeilen = [
        f"# Laufübersicht {plan.lauf_id}",
        "",
        f"Datum {plan.erstellt[:10]} · Datenstand der Noten {daten.stand or 'unbekannt'} · "
        f"Methodik {historie.methodik_version(paths)}",
        "",
        f"_{HINWEIS}_",
        "",
        "## Anfrage",
        "",
        *(f"- {art}: {text}" for art, text in plan.beschreibung),
        *([] if plan.beschreibung else ["- ganzes Universum"]),
        "",
        "## Kurzfassung",
        "",
        f"{len(rang)} Treffer, davon {len(erg.bewertet)} in diesem Lauf bewertet. Noten: "
        + ", ".join(f"{n} {noten[n]}" for n in (*NOTEN, "N", "ohne") if noten.get(n))
        + f". Kategorie Attraktiv: {attraktiv}. Tiefenanalysen: {len(erg.tiefenanalysen)}"
        f" (Grenze {plan.tief_grenze}).",
        "",
        "## Rangliste",
        "",
        "| Name | ISIN | Trade Republic | Branche | Land | Note · K · R | Kategorie | Insider |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for z in rang:
        nkr = " · ".join(_zelle(z[k]) for k in ("note", "konfidenz", "risiko"))
        zeilen.append(
            f"| {_zelle(z['name'])} | {z['isin']} | {_zelle(z['tr'])} | {_zelle(z['branche'])} "
            f"| {_zelle(z['land'])} | {nkr} | {_zelle(z['kategorie'])} | {_zelle(z['insider'])} |"
        )
    zeilen += ["", "## Tiefenanalysen", ""]
    if not erg.tiefenanalysen:
        zeilen.append("Keine (Tiefe „schnell“ oder kein Treffer mit Konfidenz K1 bis K3).")
    for isin, s in erg.tiefenanalysen.items():
        grund = f" ({s['grund']})" if s.get("grund") else ""
        zeilen.append(f"- {isin}: {s.get('status')}{grund}")
    zeilen += ["", "## Grenzen dieses Laufs", ""]
    zeilen.extend([f"- {g}" for g in erg.grenzen] or ["- keine"])
    for isin, grund in erg.fehler.items():
        zeilen.append(f"- {isin} nicht bewertet: {grund}")
    zeilen.append(
        "- Nicht in dieser Übersicht: Bewertungsbedingung, implizites Wachstum und Football Field "
        "je Titel (stehen auf der Unternehmensseite und im finanziellen Überblick)."
    )
    return "\n".join(zeilen) + "\n"


def laeufe(paths: Paths) -> list[dict[str, Any]]:
    """Alle Läufe mit Kurzfassung, neueste zuerst (Ansicht Historie)."""
    basis = paths.runs / "_laeufe"
    out = []
    for d in sorted(basis.glob("*/plan.json"), reverse=True) if basis.exists() else []:
        plan = json.loads(d.read_text("utf-8"))
        erg_datei = d.parent / "ergebnis.json"
        erg = json.loads(erg_datei.read_text("utf-8")) if erg_datei.exists() else None
        out.append(
            {
                "lauf_id": plan["lauf_id"],
                "erstellt": plan["erstellt"],
                "anfrage": [" ".join(x) for x in plan["beschreibung"]],
                "treffer": len(erg["rangliste"]) if erg else None,
                "bewertet": len(erg["bewertet"]) if erg else None,
                "tiefenanalysen": list(erg["tiefenanalysen"]) if erg else [],
                "fertig": erg is not None,
            }
        )
    return out
