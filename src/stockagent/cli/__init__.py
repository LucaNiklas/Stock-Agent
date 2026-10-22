"""Kommandozeile `stockagent` (SPEC 9.6). Je Bereich eine Datei."""

from __future__ import annotations

from stockagent.cli import (
    agents,
    analyse,
    app_cmd,
    esef,
    eskalation,
    fx,
    insider,
    markt,
    metrics,
    note,
    prices,
    sec,
    start,
    tiers,
    tr,
    universe,
    zeitplan,
)
from stockagent.cli.common import app

__all__ = ["app"]

# Die Module registrieren ihre Befehle beim Import an `app`.
_ = (
    agents,
    analyse,
    app_cmd,
    esef,
    eskalation,
    fx,
    insider,
    markt,
    metrics,
    note,
    prices,
    sec,
    tiers,
    start,
    tr,
    zeitplan,
)
_unten = universe
