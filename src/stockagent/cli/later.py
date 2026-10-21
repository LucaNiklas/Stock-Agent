"""Befehle späterer Bauschritte. Sie melden, dass sie noch nicht gebaut sind."""

from __future__ import annotations

from stockagent.cli.common import app, not_yet


@app.command()
def analyze(isin: str) -> None:
    """Finanziellen Überblick über ein Unternehmen erstellen."""
    not_yet(6, f"Die Tiefenanalyse für {isin}")
