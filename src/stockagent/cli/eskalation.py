"""Befehle `stockagent eskalationen` und `stockagent entscheiden` (SPEC 11.5, Bauschritt 10)."""

from __future__ import annotations

import json
from dataclasses import asdict

import typer

from stockagent import eskalationen, orchestrator
from stockagent.cli.common import app
from stockagent.paths import Paths


@app.command("eskalationen")
def eskalationen_zeigen(
    alle: bool = typer.Option(False, "--alle", help="Auch schon entschiedene Fälle."),
    als_json: bool = typer.Option(False, "--json", help="Ausgabe als JSON."),
) -> None:
    """Eskalierte Tiefenanalysen mit ihren Streitpunkten."""
    faelle = eskalationen.faelle(Paths.default(), alle=alle)
    if als_json:
        typer.echo(json.dumps([asdict(f) for f in faelle], ensure_ascii=False, indent=2))
        return
    if not faelle:
        typer.echo("Keine offenen Eskalationen.")
        return
    for f in faelle:
        stand = f" · entschieden: {f.entscheidung['human_decision']}" if f.entscheidung else ""
        typer.echo(f"{f.run_id} {f.name}{stand}")
        typer.echo(f"  Kategorie ohne Eskalation: {f.kategorie_vor_eskalation}")
        for s in f.streitpunkte:
            typer.echo(f"  [{s.art}] {s.text}")
            for k, v in s.werte.items():
                typer.echo(f"      {k}: {v}")


@app.command("entscheiden")
def entscheiden(
    run_id: str = typer.Argument(..., help="Lauf aus `stockagent eskalationen`."),
    entscheidung: str = typer.Argument(
        ..., help="freigeben = Streitpunkte geklärt, Bericht gilt; verwerfen = Bericht gilt nicht."
    ),
    notiz: str = typer.Option("", "--notiz", help="Begründung (human_note)."),
) -> None:
    """Deine Entscheidung zu einem eskalierten Fall speichern (state/decisions.yaml)."""
    try:
        e = eskalationen.entscheiden(Paths.default(), run_id, entscheidung.lower(), notiz)
    except (eskalationen.EskalationFehler, orchestrator.LaufFehler) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(f"{run_id}: {e['human_decision']}, Kategorie {e['kategorie']}")
