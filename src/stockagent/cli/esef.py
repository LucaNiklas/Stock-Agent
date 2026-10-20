"""Befehle `stockagent esef ...` (Bauschritt 7, SPEC 7.2)."""

from __future__ import annotations

from typing import Annotated

import typer

from stockagent import esef_update
from stockagent.cli.common import app, connect
from stockagent.paths import Paths

esef_app = typer.Typer(help="EU-Abschlussdaten aus ESEF (filings.xbrl.org).", no_args_is_help=True)
app.add_typer(esef_app, name="esef")


@esef_app.command("update")
def update(
    isin: Annotated[list[str], typer.Option("--isin", "-i", help="ISIN, mehrfach möglich.")],
) -> None:
    """Jahresberichte der letzten Jahre laden, Werte speichern und prüfen."""
    paths = Paths.default()
    connect(paths).close()
    for e in esef_update.update(paths, isin, progress=typer.echo):
        if e.fehler and not e.werte:
            typer.echo(f"{e.isin}: {e.fehler}")
            continue
        pruef = ", ".join(f"{k} {v}" for k, v in sorted(e.flags.items()))
        typer.echo(
            f"{e.isin} {e.issuer_id}: {e.einreichungen} Berichte, {e.werte} Werte, "
            f"Prüfungen: {pruef}" + (f" ({e.fehler})" if e.fehler else "")
        )
