"""Befehle der Tiefenanalyse (Bauschritt 6, SPEC 15.1): analyze, next, accept, runs, tool."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from stockagent import orchestrator
from stockagent.agents.tools import nachrechnen
from stockagent.cli.common import app, connect
from stockagent.paths import Paths

tool_app = typer.Typer(help="Werkzeuge für Agenten (nur lesen, SPEC 16.1).", no_args_is_help=True)
app.add_typer(tool_app, name="tool")


def _vorlage(paths: Paths, agent: str) -> str:
    return str(orchestrator.modelle(paths)["tiefenanalyse"]["agenten"][agent]["vorlage"])


@app.command()
def analyze(isin: str) -> None:
    """Tiefenanalyse anlegen: Daten, Note und Berichte in Python, dann Plan der Agenten.

    Ausführen in Claude Code mit /analyze-stock <ISIN> (führt alle Schritte aus)."""
    paths = Paths.default()
    connect(paths).close()
    try:
        z = orchestrator.anlegen(paths, isin, progress=typer.echo)
    except orchestrator.LaufFehler as exc:
        typer.echo(f"Abbruch: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"Lauf {z.run_id} angelegt: {len(z.auftraege)} Aufträge, {len(z.dokumente)} Berichte"
    )
    typer.echo(f"Nächster Schritt: uv run stockagent next {z.run_id}")


@app.command("next")
def next_cmd(
    run_id: str,
    als_json: Annotated[
        bool, typer.Option("--json", help="Maschinenlesbar für den Skill.")
    ] = False,
) -> None:
    """Fällige Aufträge nennen (und beauftragen). Leer, wenn der Lauf fertig ist."""
    paths = Paths.default()
    try:
        auftraege = orchestrator.naechste(paths, run_id)
        z = orchestrator.laden(paths, run_id)
    except orchestrator.LaufFehler as exc:
        typer.echo(f"Abbruch: {exc}")
        raise typer.Exit(code=1) from exc
    liste = [
        {
            "auftrag": a.id,
            "subagent": _vorlage(paths, a.agent),
            "eingabe": a.eingabe,
            "versuche": a.versuche,
            "prompt": f"Lies die Auftragsdatei {a.eingabe} und bearbeite den Auftrag. "
            "Antworte ausschließlich mit dem JSON-Objekt nach dem Schema aus der Datei.",
        }
        for a in auftraege
    ]
    ergebnis = {
        "run_id": run_id,
        "status": z.status,
        "grund": z.grund,
        "auftraege": liste,
        "bericht": f"runs/{run_id}/report.html" if z.status != "laeuft" else None,
    }
    if als_json:
        typer.echo(json.dumps(ergebnis, ensure_ascii=False, indent=2))
        return
    typer.echo(f"Lauf {run_id}: {z.status}" + (f" ({z.grund})" if z.grund else ""))
    for x in liste:
        typer.echo(f"  {x['auftrag']}: Subagent {x['subagent']}, Eingabe {x['eingabe']}")
    if ergebnis["bericht"]:
        typer.echo(f"Bericht: {ergebnis['bericht']}")


@app.command()
def accept(
    run_id: Annotated[str | None, typer.Argument()] = None,
    auftrag: Annotated[str | None, typer.Argument()] = None,
    datei: Annotated[
        Path | None, typer.Option("--datei", help="Antwort des Agenten als Datei.")
    ] = None,
    hook: Annotated[
        bool, typer.Option("--hook", help="Aufruf aus dem Stop-Hook eines Subagents (stdin).")
    ] = False,
) -> None:
    """Antwort eines Agenten prüfen und annehmen (Schema und Schranken, SPEC 12.6)."""
    paths = Paths.default()
    if hook:
        daten = json.loads(sys.stdin.read() or "{}")
        text = str(daten.get("last_assistant_message") or "")
        from stockagent.agents.runner import auftrag_aus_text

        kennung = auftrag_aus_text(text)
        if not kennung or "/" not in kennung:
            return  # keine Antwort einer Tiefenanalyse
        run_id, auftrag = kennung.rsplit("/", 1)
    elif datei is not None:
        text = datei.read_text("utf-8")
    else:
        text = sys.stdin.read()
    if not run_id:
        typer.echo("Lauf fehlt")
        raise typer.Exit(code=1)
    try:
        erg = orchestrator.annehmen(paths, run_id, text, auftrag)
    except orchestrator.LaufFehler as exc:
        if hook:
            return
        typer.echo(f"Abbruch: {exc}")
        raise typer.Exit(code=1) from exc
    if erg.angenommen or erg.eskaliert:
        typer.echo(erg.meldung)
        return
    # Abgelehnt: Exit-Code 2 schickt die Meldung im Hook an den Agenten zurück
    typer.echo(erg.meldung, err=True)
    raise typer.Exit(code=2)


@app.command()
def runs() -> None:
    """Tiefenanalysen mit Stand."""
    paths = Paths.default()
    for z in orchestrator.laufende(paths):
        f = orchestrator.fortschritt(z)
        teile = ", ".join(
            f"{abt} {sum(v.values())}/{v.get('angenommen', 0)}"
            for abt, v in f["abteilungen"].items()
        )
        typer.echo(f"{z.run_id}  {z.name[:30]:30}  {z.status:12}  {teile}")


@tool_app.command("rechenweg")
def tool_rechenweg(isin: str, ref: str) -> None:
    """Gespeicherter Rechenweg einer Zahl, etwa ebit_margin@2025 oder pe@aktuell."""
    typer.echo(json.dumps(nachrechnen.rechenweg(Paths.default(), isin, ref), ensure_ascii=False))


@tool_app.command("nachrechnen")
def tool_nachrechnen(isin: str, refs: list[str]) -> None:
    """Werte neu aus den Abschlusswerten rechnen (J1, blind)."""
    erg = nachrechnen.nachrechnen(Paths.default(), isin, refs)
    typer.echo(json.dumps(erg, ensure_ascii=False, indent=1))
