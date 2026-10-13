"""Befehl `stockagent tr-check` (Lucas Prüfung in der Trade-Republic-App)."""

from __future__ import annotations

from datetime import date

import typer

from stockagent import tr_checks
from stockagent.cli.common import app
from stockagent.data import store
from stockagent.paths import Paths
from stockagent.report import universe_view


@app.command("tr-check")
def tr_check(
    isin: str = typer.Argument(..., help="ISIN der Aktie."),
    answer: str = typer.Argument(..., help="ja = in der App handelbar, nein = nicht handelbar."),
) -> None:
    """Ergebnis deiner Prüfung in der Trade-Republic-App festhalten."""
    if answer.lower() not in ("ja", "nein"):
        typer.echo("Antwort muss 'ja' oder 'nein' sein.")
        raise typer.Exit(code=1)
    paths = Paths.default()
    if paths.db.exists():
        conn = store.connect(paths.db)
        known = store.is_listed(conn, isin.upper())
        conn.close()
        if not known:
            typer.echo(f"Hinweis: {isin.upper()} steht nicht in der aktuellen Liste.")
    try:
        check = tr_checks.record(
            paths.tr_checks, isin.upper(), answer.lower() == "ja", date.today()
        )
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"{isin.upper()}: {universe_view.TR_LABEL[check.status]} ({check.checked_on:%d.%m.%Y})"
    )
