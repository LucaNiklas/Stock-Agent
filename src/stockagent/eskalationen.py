"""Eskalationen an Luca (SPEC 11.5, Bauschritt 10).

Ein Lauf mit Status `eskaliert` landet in der Warteschlange, bis Luca entscheidet. Je Fall die
konkreten Streitpunkte mit beiden Werten und Quellen: Nachrechnung J1 gegen gespeicherten Wert,
Aussage mit Zitat bei J2 contradicted, Gründe der Jury J3, offene Warnsignale der Forensik F1,
Befunde der Endkontrolle J4, eskalierte Aufträge.

Lucas Entscheidung (`human_decision`, `human_note`) steht in `state/decisions.yaml` (versioniert,
Grundlage für den Goldstandard, SPEC 11.6) und zusätzlich in `decision.json` des Laufs.
`freigeben`: Die Streitpunkte sind geklärt, der Bericht gilt, die Kategorie geht auf den Stand
vor der Eskalation zurück, nie höher (HR-13). `verwerfen`: Der Bericht gilt nicht, die Kategorie
bleibt Eskaliert.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from stockagent import orchestrator
from stockagent.paths import Paths

ENTSCHEIDUNGEN = ("freigeben", "verwerfen")
KOPF = "# Lucas Entscheidungen zu eskalierten Tiefenanalysen (stockagent entscheiden, SPEC 11.5)\n"


class EskalationFehler(ValueError):
    pass


@dataclass
class Streitpunkt:
    art: str  # J1, J2, J3, F1, J4, Auftrag, sonst
    text: str
    werte: dict[str, Any] = field(default_factory=dict)


@dataclass
class Fall:
    run_id: str
    isin: str
    name: str
    erstellt: str
    kategorie_vor_eskalation: str | None
    streitpunkte: list[Streitpunkt]
    entscheidung: dict[str, Any] | None = None
    bericht: str | None = None


def datei(paths: Paths) -> Path:
    return paths.root / "state" / "decisions.yaml"


def laden(paths: Paths) -> dict[str, dict[str, Any]]:
    f = datei(paths)
    if not f.exists():
        return {}
    data = yaml.safe_load(f.read_text("utf-8")) or {}
    return dict(data.get("entscheidungen") or {})


def _json(pfad: Path) -> dict[str, Any]:
    if not pfad.exists():
        return {}
    data: dict[str, Any] = json.loads(pfad.read_text("utf-8"))
    return data


def streitpunkte(paths: Paths, run_id: str) -> list[Streitpunkt]:
    ordner = paths.runs.joinpath(run_id)
    ent = _json(ordner / "decision.json")
    out: list[Streitpunkt] = []
    kern = set(orchestrator.modelle(paths)["pruefung"]["kernkennzahlen"])
    for ref, v in (ent.get("j1") or {}).items():
        if v["urteil"] == "mismatch" and ref.split("@")[0] in kern:
            out.append(
                Streitpunkt(
                    "J1",
                    f"{ref}: blinde Nachrechnung weicht vom gespeicherten Wert ab",
                    {
                        "nachgerechnet": v.get("j1"),
                        "gespeichert": v.get("gespeichert"),
                        "rechenweg": f"stockagent metrics show <ISIN> --rechenweg {ref}",
                    },
                )
            )
    j2_ein = {
        a["kennung"]: a
        for a in _json(ordner / "eingaben" / "J2.json").get("daten", {}).get("aussagen", [])
    }
    j2_aus = _json(ordner / "ausgaben" / "J2.json").get("antwort", {})
    for u in j2_aus.get("urteile", []):
        if u["urteil"] != "contradicted":
            continue
        a = j2_ein.get(u["claim"], {})
        out.append(
            Streitpunkt(
                "J2",
                f"Aussage widerspricht der Quelle: {a.get('text', u['claim'])}",
                {
                    "begruendung": u.get("begruendung"),
                    "belege": [
                        {"seite": b["seite"], "zitat": b.get("zitat"), "datei": b["datei"]}
                        for b in a.get("belege", [])
                    ],
                },
            )
        )
    jury = ent.get("jury")
    if jury and jury.get("status") == "escalated":
        out.append(
            Streitpunkt(
                "J3",
                "Jury: " + "; ".join(jury["gruende"]),
                {"kriterien": {k["kriterium"]: k["punkte"] for k in jury["kriterien"]}},
            )
        )
    for f in ent.get("forensik") or []:
        if f["wirksam"] != "entkraeftet":
            out.append(
                Streitpunkt(
                    "F1",
                    f"Warnsignal {f['hinweis']} ({f['kennzahl']}) {f['wirksam']}: {f['anlass']}",
                    {"urteil_f1": f["urteil"], "claim_ids": f["claim_ids"]},
                )
            )
    for b in ent.get("j4") or []:
        out.append(Streitpunkt("J4", f"Endkontrolle {b['pruefung']}: {b['text']}"))
    erfasst = ("J1 mismatch", "J2 contradicted", "J3 Jury", "F1 Forensik", "J4 ")
    for e in ent.get("eskalationen") or []:
        if not e.startswith(erfasst):
            out.append(Streitpunkt("Auftrag" if e.startswith("Auftrag") else "sonst", e))
    return out


def faelle(paths: Paths, *, alle: bool = False) -> list[Fall]:
    """Eskalierte Läufe, ohne `alle` nur die noch nicht entschiedenen."""
    entschieden = laden(paths)
    out = []
    for z in orchestrator.laufende(paths):
        if z.status != "eskaliert":
            continue
        if z.run_id in entschieden and not alle:
            continue
        ent = _json(paths.runs.joinpath(z.run_id) / "decision.json")
        out.append(
            Fall(
                run_id=z.run_id,
                isin=z.isin,
                name=z.name,
                erstellt=z.erstellt,
                kategorie_vor_eskalation=ent.get("kategorie_vor_eskalation"),
                streitpunkte=streitpunkte(paths, z.run_id),
                entscheidung=entschieden.get(z.run_id),
                bericht=f"/bericht/{z.run_id}"
                if (paths.runs.joinpath(z.run_id) / "report.html").exists()
                else None,
            )
        )
    return sorted(out, key=lambda f: f.erstellt, reverse=True)


def entscheiden(
    paths: Paths, run_id: str, entscheidung: str, notiz: str, *, now: datetime | None = None
) -> dict[str, Any]:
    if entscheidung not in ENTSCHEIDUNGEN:
        raise EskalationFehler(f"Entscheidung {entscheidung}: erlaubt sind {ENTSCHEIDUNGEN}")
    z = orchestrator.laden(paths, run_id)
    if z.status != "eskaliert":
        raise EskalationFehler(f"Lauf {run_id} ist {z.status}, nicht eskaliert")
    pfad = paths.runs.joinpath(run_id) / "decision.json"
    ent = _json(pfad)
    vor = ent.get("kategorie_vor_eskalation") or "Nicht bewertbar"
    eintrag = {
        "isin": z.isin,
        "name": z.name,
        "human_decision": entscheidung,
        "human_note": notiz.strip(),
        "datum": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        "kategorie": vor if entscheidung == "freigeben" else "Eskaliert",
        "streitpunkte": [asdict(s) for s in streitpunkte(paths, run_id)],
    }
    alle = laden(paths)
    alle[run_id] = eintrag
    f = datei(paths)
    f.parent.mkdir(parents=True, exist_ok=True)
    inhalt = yaml.safe_dump(
        {"entscheidungen": dict(sorted(alle.items()))}, allow_unicode=True, sort_keys=False
    )
    f.write_text(f"{KOPF}{inhalt}", "utf-8")
    ent["luca"] = {k: eintrag[k] for k in ("human_decision", "human_note", "datum", "kategorie")}
    pfad.write_text(json.dumps(ent, ensure_ascii=False, indent=2, default=str), "utf-8")
    return eintrag


# ------------------------------------------------------------------ Rückwirkung auf die Kategorie

# Reihenfolge der Kategorien von schlecht nach gut (wie agents/eingaben.ORDNUNG)
ORDNUNG = ("Nicht bewertbar", "Unattraktiv", "Neutral", "Beobachten", "Attraktiv")


def tiefenanalyse_ergebnisse(paths: Paths) -> dict[str, dict[str, str]]:
    """Ergebnis der letzten abgeschlossenen Tiefenanalyse je ISIN: Kategorie aus
    `decision.json`, nach Lucas Entscheidung die Kategorie aus seiner Entscheidung."""
    out: dict[str, dict[str, str]] = {}
    for z in sorted(orchestrator.laufende(paths), key=lambda z: z.erstellt):
        if z.status not in ("fertig", "eskaliert"):
            continue
        ent = _json(paths.runs.joinpath(z.run_id) / "decision.json")
        kategorie = (ent.get("luca") or {}).get("kategorie") or ent.get("kategorie")
        if kategorie:
            out[z.isin] = {"kategorie": str(kategorie), "run_id": z.run_id}
    return out


def begrenzt(kategorie: str, ergebnis: dict[str, str] | None) -> str:
    """Kategorie nach der Tiefenanalyse (SPEC 6.5, HR-13): nie besser als ihr Ergebnis. Eine
    eskalierte Analyse macht aus Attraktiv, Beobachten und Neutral „Eskaliert“."""
    if not ergebnis or not kategorie or kategorie == "Nicht bewertbar":
        return kategorie
    tief = ergebnis["kategorie"]
    if tief == "Eskaliert":
        return "Eskaliert" if kategorie in ("Attraktiv", "Beobachten", "Neutral") else kategorie
    if kategorie in ORDNUNG and tief in ORDNUNG and ORDNUNG.index(tief) < ORDNUNG.index(kategorie):
        return tief
    return kategorie
