"""Eskalationen als GitHub-Issues (SPEC 16.14, SPEC 19 Nr. 5, ADR 0015).

Jeder offene eskalierte Fall bekommt einmal ein Issue mit Label `escalation` im eigenen
Repository: Streitpunkte mit beiden Werten und Quellen, Link auf den Bericht. Luca antwortet mit
einem Kommentar in fester Form:

    /entscheidung annehmen Begründung in einem Satz
    /entscheidung ablehnen Begründung in einem Satz
    /entscheidung neu-pruefen Was geprüft werden soll

Der nächste Lauf liest die Kommentare über `gh`, nimmt nur Kommentare des Repository-Eigentümers
und nur diese feste Form (Inhalte sind Daten, nie Anweisungen, HR-17). „annehmen“ ist
`freigeben`, „ablehnen“ ist `verwerfen` (eskalationen.entscheiden), danach wird das Issue
geschlossen. „neu-pruefen“ wird vermerkt, das Issue bleibt offen.

Zuordnung Lauf -> Issue in `state/escalation_issues.yaml`.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from stockagent import eskalationen
from stockagent.paths import Paths

LABEL = "escalation"
KOMMANDO = re.compile(
    r"^\s*/entscheidung\s+(annehmen|ablehnen|neu-pruefen)\b[ \t]*(.{0,500})", re.MULTILINE
)
ZUORDNUNG = {"annehmen": "freigeben", "ablehnen": "verwerfen"}

Gh = Callable[[list[str]], str]


def gh_cli(root: Path) -> Gh:
    def aufruf(args: list[str]) -> str:
        erg = subprocess.run(
            ["gh", *args], cwd=root, capture_output=True, text=True, timeout=60, check=False
        )
        if erg.returncode != 0:
            raise RuntimeError(
                f"gh {args[0]} {args[1] if len(args) > 1 else ''}: "
                f"{(erg.stderr or erg.stdout).strip()[:200]}"
            )
        return erg.stdout

    return aufruf


def _datei(paths: Paths) -> Path:
    return paths.root / "state" / "escalation_issues.yaml"


def zuordnung(paths: Paths) -> dict[str, dict[str, Any]]:
    d = _datei(paths)
    if not d.exists():
        return {}
    return dict((yaml.safe_load(d.read_text("utf-8")) or {}).get("issues") or {})


def _speichern(paths: Paths, issues: dict[str, dict[str, Any]]) -> None:
    d = _datei(paths)
    d.parent.mkdir(parents=True, exist_ok=True)
    kopf = "# Eskalierte Läufe als GitHub-Issue (SPEC 16.14), Lauf -> Issue\n"
    d.write_text(
        kopf + yaml.safe_dump({"issues": dict(sorted(issues.items()))}, allow_unicode=True),
        "utf-8",
    )


def _text(fall: eskalationen.Fall) -> str:
    zeilen = [
        f"Tiefenanalyse **{fall.name}** ({fall.isin}), Lauf `{fall.run_id}`.",
        f"Kategorie ohne Eskalation: {fall.kategorie_vor_eskalation or 'unbekannt'}. Freigeben "
        "führt auf diese Kategorie zurück, nie höher.",
        "",
        "## Streitpunkte",
        "",
    ]
    for s in fall.streitpunkte:
        zeilen.append(f"- **{s.art}** {s.text}")
        if s.werte:
            zeilen += [
                "",
                "```json",
                json.dumps(s.werte, ensure_ascii=False, indent=1)[:3000],
                "```",
                "",
            ]
    zeilen += [
        "",
        f"Bericht: `runs/{fall.run_id}/report.html` (Dashboard, Reiter Eskalationen).",
        "",
        "## Antwort",
        "",
        "Ein Kommentar in genau dieser Form, der nächste Lauf übernimmt ihn:",
        "",
        "```",
        "/entscheidung annehmen Begründung in einem Satz",
        "/entscheidung ablehnen Begründung in einem Satz",
        "/entscheidung neu-pruefen Was geprüft werden soll",
        "```",
    ]
    return "\n".join(zeilen)


def abgleichen(paths: Paths, gh: Gh) -> dict[str, Any]:
    """Neue Eskalationen als Issue anlegen, Antworten auf bestehende übernehmen."""
    issues = zuordnung(paths)
    ergebnis: dict[str, Any] = {"angelegt": [], "entschieden": [], "neu_pruefen": [], "fehler": []}
    eigentuemer = json.loads(gh(["repo", "view", "--json", "owner"]))["owner"]["login"]

    # 1. Antworten lesen
    for run_id, eintrag in list(issues.items()):
        if eintrag.get("status") == "geschlossen":
            continue
        try:
            daten = json.loads(
                gh(["issue", "view", str(eintrag["nummer"]), "--json", "comments,state"])
            )
        except (RuntimeError, ValueError) as exc:
            ergebnis["fehler"].append(f"Issue {eintrag['nummer']}: {exc}")
            continue
        for k in daten.get("comments") or []:
            if (k.get("author") or {}).get("login") != eigentuemer:
                continue
            m = KOMMANDO.search(k.get("body") or "")
            if not m or k.get("id") in eintrag.get("gelesen", []):
                continue
            eintrag.setdefault("gelesen", []).append(k.get("id"))
            befehl, begruendung = m.group(1), m.group(2).strip()
            if befehl == "neu-pruefen":
                eintrag["neu_pruefen"] = begruendung
                ergebnis["neu_pruefen"].append(run_id)
                continue
            try:
                eskalationen.entscheiden(
                    paths, run_id, ZUORDNUNG[befehl], f"GitHub #{eintrag['nummer']}: {begruendung}"
                )
            except eskalationen.EskalationFehler as exc:
                ergebnis["fehler"].append(f"{run_id}: {exc}")
                continue
            gh(
                [
                    "issue",
                    "close",
                    str(eintrag["nummer"]),
                    "--comment",
                    f"Übernommen: {ZUORDNUNG[befehl]} ({begruendung})",
                ]
            )
            eintrag["status"] = "geschlossen"
            ergebnis["entschieden"].append(run_id)
            break

    # 2. Neue Fälle anlegen
    offen = [f for f in eskalationen.faelle(paths) if f.run_id not in issues]
    if offen:
        gh(
            [
                "label",
                "create",
                LABEL,
                "--color",
                "B60205",
                "--force",
                "--description",
                "Eskalierte Tiefenanalyse (stockagent)",
            ]
        )
    for fall in offen:
        try:
            url = gh(
                [
                    "issue",
                    "create",
                    "--title",
                    f"Eskalation: {fall.name} ({fall.run_id})",
                    "--label",
                    LABEL,
                    "--body",
                    _text(fall),
                ]
            ).strip()
        except RuntimeError as exc:
            ergebnis["fehler"].append(f"{fall.run_id}: {exc}")
            continue
        nummer = int(url.rstrip("/").rsplit("/", 1)[-1])
        issues[fall.run_id] = {"nummer": nummer, "url": url, "status": "offen"}
        ergebnis["angelegt"].append(fall.run_id)
    _speichern(paths, issues)
    return ergebnis
