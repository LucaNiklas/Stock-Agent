"""Befehle späterer Bauschritte. Sie melden, dass sie noch nicht gebaut sind."""

from __future__ import annotations

from stockagent.cli.common import app, not_yet


@app.command()
def run() -> None:
    """Lauf über alle Titel mit Laufplan („Alle bewerten“)."""
    not_yet(11, "Der Lauf über alle Titel")
