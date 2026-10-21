"""Claude Code im Hintergrund über Lucas Abo (SPEC 13.5, 15.1).

Zwei Aufrufe, beide ohne Rückfragen und mit festen Rechten:
- Tiefenanalyse: `claude -p "/analyze-stock <ISIN>"` mit den Werkzeugen aus `ERLAUBTE_WERKZEUGE`.
- Übersetzen eines Satzes in einen Filter (SPEC 9.9): `claude -p` mit `--json-schema`, ohne
  Werkzeuge. Die Antwort ist ein Vorschlag, den `anfrage.pruefen` gegen die Listen prüft.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Rechte der Tiefenanalyse: nur das CLI, Lesen, Schreiben unter runs/, Subagents. Die Rechte der
# Subagents selbst stehen in ihrem Frontmatter (.claude/agents/).
ERLAUBTE_WERKZEUGE = [
    "Bash(uv run stockagent *)",
    "Read",
    "Grep",
    "Write(./runs/**)",
    "Agent",
    "WebSearch",
    "WebFetch",
]

# Übliche Installationsorte, falls `claude` nicht im PATH liegt (etwa wenn das Dashboard per
# Doppelklick startet und die Shell-Einstellungen nicht gelesen werden).
ORTE = (
    "~/.claude/local/claude",
    "~/.local/bin/claude",
    "/opt/homebrew/bin/claude",
    "/usr/local/bin/claude",
)


class ClaudeFehler(RuntimeError):
    pass


def pfad() -> str | None:
    """Pfad zu `claude` oder None, wenn Claude Code nicht installiert ist."""
    if gefunden := shutil.which("claude"):
        return gefunden
    for ort in ORTE:
        p = Path(ort).expanduser()
        if p.is_file():
            return str(p)
    return None


def analyse_befehl(isin: str) -> list[str]:
    """Befehl der Tiefenanalyse. Rechte nur über `ERLAUBTE_WERKZEUGE`."""
    return [
        pfad() or "claude",
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


Runner = Callable[..., Any]


def strukturiert(
    prompt: str,
    schema: dict[str, Any],
    modell: str,
    *,
    runner: Runner = subprocess.run,
    timeout: int = 120,
) -> dict[str, Any]:
    """Ein Aufruf ohne Werkzeuge mit festem Antwortschema. Gibt die Antwort als dict zurück."""
    befehl = [
        pfad() or "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(schema, ensure_ascii=False),
        "--model",
        modell,
        "--tools",
        "",
    ]
    try:
        erg = runner(
            befehl,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ClaudeFehler(f"Claude Code nicht erreichbar: {exc}") from exc
    if erg.returncode != 0:
        raise ClaudeFehler(f"Claude Code meldet Fehler: {(erg.stderr or erg.stdout)[:300]}")
    try:
        daten = json.loads(erg.stdout)
    except json.JSONDecodeError as exc:
        raise ClaudeFehler("Antwort von Claude Code ist kein JSON") from exc
    if isinstance(daten, dict) and daten.get("is_error"):
        raise ClaudeFehler(f"Claude Code meldet Fehler: {str(daten.get('result'))[:300]}")
    antwort = daten.get("structured_output") if isinstance(daten, dict) else None
    if antwort is None and isinstance(daten, dict) and isinstance(daten.get("result"), str):
        try:
            antwort = json.loads(daten["result"])
        except json.JSONDecodeError as exc:
            raise ClaudeFehler("Antwort ohne strukturierten Teil") from exc
    if not isinstance(antwort, dict):
        raise ClaudeFehler("Antwort ohne strukturierten Teil")
    return antwort
