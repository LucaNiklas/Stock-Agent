"""Kommandozeile `stockagent` (SPEC 9.6). Je Bereich eine Datei."""

from __future__ import annotations

from stockagent.cli import agents, fx, later, metrics, prices, sec, tr, universe
from stockagent.cli.common import app

__all__ = ["app"]

# Die Module registrieren ihre Befehle beim Import an `app`.
_ = (agents, fx, later, metrics, prices, sec, tr, universe)
