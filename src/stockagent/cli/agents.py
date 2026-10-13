"""Befehl `stockagent render-agents` (SPEC 16.4)."""

from __future__ import annotations

import typer

from stockagent.agents.render import RenderError, render_all
from stockagent.cli.common import app
from stockagent.paths import Paths


@app.command("render-agents")
def render_agents() -> None:
    """Agent-Dateien aus agents_src/ mit Modell aus config/models.yaml erzeugen (SPEC 16.4)."""
    paths = Paths.default()
    try:
        written = render_all(
            paths.root / "agents_src",
            paths.root / ".claude" / "agents",
            paths.config / "models.yaml",
        )
    except RenderError as exc:
        typer.echo(f"Abbruch: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"{len(written)} Agent-Dateien erzeugt.")
