"""Befehle späterer Bauschritte. Sie melden, dass sie noch nicht gebaut sind."""

from __future__ import annotations

from stockagent.cli.common import app, not_yet


@app.command()
def screen() -> None:
    """Noten für alle Unternehmen berechnen, ohne Modellaufrufe."""
    not_yet(5, "Die Notenberechnung")


@app.command()
def analyze(isin: str) -> None:
    """Finanziellen Überblick über ein Unternehmen erstellen."""
    not_yet(6, f"Die Tiefenanalyse für {isin}")


@app.command()
def status() -> None:
    """Letzte Läufe und offene Eskalationen anzeigen."""
    not_yet(5, "Die Statusanzeige")


@app.command()
def dashboard() -> None:
    """Dashboard bauen und öffnen."""
    not_yet(5, "Das Dashboard")
