"""Kommandozeile `stockagent` (SPEC 9.6). In Schritt 0 nur das Gerüst."""

from __future__ import annotations

import typer

from stockagent import __version__

app = typer.Typer(
    help="Recherche- und Bewertungssystem für bei Trade Republic handelbare Aktien.",
    no_args_is_help=True,
)


def _not_yet(step: int, what: str) -> None:
    typer.echo(f"{what} ist noch nicht gebaut (Bauschritt {step}, siehe docs/spec/16-*.md).")
    raise typer.Exit(code=2)


@app.command()
def version() -> None:
    """Version anzeigen."""
    typer.echo(__version__)


@app.command()
def universe() -> None:
    """Liste der bei Trade Republic handelbaren Aktien laden."""
    _not_yet(1, "Das Universum")


@app.command()
def screen() -> None:
    """Noten für alle Unternehmen berechnen, ohne Modellaufrufe."""
    _not_yet(5, "Die Notenberechnung")


@app.command()
def analyze(isin: str) -> None:
    """Finanziellen Überblick über ein Unternehmen erstellen."""
    _not_yet(6, f"Die Tiefenanalyse für {isin}")


@app.command()
def status() -> None:
    """Letzte Läufe und offene Eskalationen anzeigen."""
    _not_yet(5, "Die Statusanzeige")


@app.command()
def dashboard() -> None:
    """Dashboard bauen und öffnen."""
    _not_yet(5, "Das Dashboard")
