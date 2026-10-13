"""Gemeinsame Teile der Kommandozeile."""

from __future__ import annotations

import duckdb
import typer
from rich.console import Console

from stockagent import __version__
from stockagent.data import store
from stockagent.paths import Paths

app = typer.Typer(
    help="Recherche- und Bewertungssystem für bei Trade Republic handelbare Aktien.",
    no_args_is_help=True,
)
console = Console()


def not_yet(step: int, what: str) -> None:
    typer.echo(f"{what} ist noch nicht gebaut (Bauschritt {step}, siehe docs/spec/16-*.md).")
    raise typer.Exit(code=2)


@app.command()
def version() -> None:
    """Version anzeigen."""
    typer.echo(__version__)


def connect(paths: Paths) -> duckdb.DuckDBPyConnection:
    if not paths.db.exists():
        typer.echo("Noch keine Liste geladen. Zuerst: stockagent universe update")
        raise typer.Exit(code=1)
    try:
        return store.connect(paths.db)
    except store.SchemaOutdated as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
