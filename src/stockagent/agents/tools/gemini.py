"""Gemini als zweite Modellfamilie für Prüfer (SPEC 8.8, Bauschritt 10, ADR 0013).

Aufruf über die Gemini CLI im nicht-interaktiven Modus (`gemini -p`), angemeldet mit Lucas
Google-Konto. Eingabe: Text der Prüfer-Vorlage, Auftragsdatei und die Seiten, auf die sie
verweist, alles im Aufruf selbst (Gemini braucht keine Werkzeuge und keinen Dateizugriff).
Ausgabe: JSON, gegen das Antwortschema geprüft.

Nicht verfügbar (CLI fehlt, `extern.aktiv` aus, Anmeldung oder Kontingent gescheitert, Antwort
ohne gültiges JSON): `GeminiNichtVerfuegbar`. Der Aufrufer nimmt dann das Rückfallmodell aus
`config/models.yaml` und der Bericht weist auf die eingeschränkte Diversität hin (HR-16).

Gemini bekommt nur öffentliche Unternehmensdaten, nie persönliche Daten (SPEC 8.8). Ein
API-Schlüssel mit Abrechnung wird nur nach Lucas ausdrücklicher Entscheidung genutzt (SPEC 19).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from stockagent.agents.runner import json_aus_text
from stockagent.schemas.agents import ANTWORTEN

Aufruf = Callable[[list[str]], subprocess.CompletedProcess[str]]
ZEITLIMIT_SEKUNDEN = 600


class GeminiNichtVerfuegbar(RuntimeError):
    pass


def _aufruf(befehl: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(befehl, capture_output=True, text=True, timeout=ZEITLIMIT_SEKUNDEN)


def verfuegbar(models_cfg: dict[str, Any]) -> tuple[bool, str]:
    if not models_cfg.get("extern", {}).get("aktiv", False):
        return False, "extern.aktiv ist aus (config/models.yaml)"
    if shutil.which("gemini") is None:
        return False, "Gemini CLI nicht installiert"
    return True, "bereit"


def _vorlage_ohne_kopf(vorlage: Path) -> str:
    text = vorlage.read_text("utf-8")
    return text.split("---\n", 2)[2] if text.startswith("---\n") else text


def auftrag_text(root: Path, vorlage: Path, eingabe: Path) -> str:
    """Prompt: Rolle aus der Vorlage, Auftrag und die genannten Seitendateien als Daten."""
    auftrag = json.loads(eingabe.read_text("utf-8"))
    seiten = []
    for a in auftrag.get("daten", {}).get("aussagen", []):
        for b in a.get("belege", []):
            datei = root.joinpath(b["datei"])
            if datei.exists():
                seiten.append(f"=== Datei {b['datei']} ===\n{datei.read_text('utf-8')}")
    return "\n\n".join(
        [
            _vorlage_ohne_kopf(vorlage).strip(),
            "Die Auftragsdatei und die Seiten stehen unten. Du hast keine Werkzeuge. Antworte "
            "ausschließlich mit dem JSON-Objekt.",
            f"=== Auftragsdatei {eingabe.relative_to(root)} ===\n"
            + json.dumps(auftrag, ensure_ascii=False, indent=1),
            *seiten,
        ]
    )


def pruefen(
    root: Path,
    agent: str,
    vorlage: Path,
    eingabe: Path,
    models_cfg: dict[str, Any],
    *,
    aufruf: Aufruf = _aufruf,
    pruefe_verfuegbar: bool = True,
) -> str:
    """Antworttext (JSON) eines Prüfers über Gemini, gegen das Schema von `agent` geprüft."""
    if pruefe_verfuegbar:
        ok, grund = verfuegbar(models_cfg)
        if not ok:
            raise GeminiNichtVerfuegbar(grund)
    befehl = ["gemini", "-p", auftrag_text(root, vorlage, eingabe), "--output-format", "json"]
    try:
        erg = aufruf(befehl)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GeminiNichtVerfuegbar(f"Aufruf gescheitert: {exc}") from exc
    if erg.returncode != 0:
        raise GeminiNichtVerfuegbar(f"gemini beendet mit {erg.returncode}: {erg.stderr[-300:]}")
    try:
        antwort = str(json.loads(erg.stdout).get("response", ""))
        text = json_aus_text(antwort)
        ANTWORTEN[agent].model_validate_json(text)
    except (ValueError, ValidationError) as exc:
        raise GeminiNichtVerfuegbar(f"Antwort ohne gültiges JSON: {str(exc)[:300]}") from exc
    return text


def test(aufruf: Aufruf = _aufruf) -> dict[str, Any]:
    """Praktischer Test auf Lucas Mac (SPEC 8.8): CLI da, Anmeldung gültig, JSON-Ausgabe."""
    if shutil.which("gemini") is None:
        return {"ok": False, "grund": "Gemini CLI nicht installiert (npm i -g @google/gemini-cli)"}
    try:
        erg = aufruf(["gemini", "-p", 'Antworte nur mit {"ok": true}', "--output-format", "json"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "grund": f"Aufruf gescheitert: {exc}"}
    if erg.returncode != 0:
        return {"ok": False, "grund": f"Exit {erg.returncode}: {erg.stderr[-300:]}"}
    try:
        daten = json.loads(erg.stdout)
        json.loads(json_aus_text(str(daten.get("response", ""))))
    except ValueError as exc:
        return {"ok": False, "grund": f"keine JSON-Antwort: {exc}"}
    return {"ok": True, "grund": "Gemini antwortet mit JSON", "statistik": daten.get("stats")}
