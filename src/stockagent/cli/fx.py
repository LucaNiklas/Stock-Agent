"""Befehle `stockagent fx ...` (Bauschritt 4, Wechselkurse der EZB)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import typer

from stockagent import fx_update
from stockagent.cli.common import app, connect
from stockagent.core.anzeige import formatiere
from stockagent.data import store
from stockagent.data.http import FetchError
from stockagent.data.sources.fx import EcbFormatError
from stockagent.paths import Paths

fx_app = typer.Typer(help="Wechselkurse der EZB laden und anzeigen.", no_args_is_help=True)
app.add_typer(fx_app, name="fx")


@fx_app.command("update")
def update(
    refresh: bool = typer.Option(False, "--refresh", help="Auch abrufen, wenn heute schon."),
) -> None:
    """Referenzkurse der EZB laden (beim ersten Mal ab 2015, danach nur Neues)."""
    paths = Paths.default()
    connect(paths).close()
    try:
        res = fx_update.update(paths, refresh=refresh)
    except (FetchError, EcbFormatError) as exc:
        typer.echo(f"Abbruch: {exc}")
        raise typer.Exit(code=1) from exc
    if res.uebersprungen:
        typer.echo(f"Wechselkurse schon aktuell (bis {res.bis:%d.%m.%Y}).")
    else:
        bis = f"{res.bis:%d.%m.%Y}" if res.bis else "-"
        typer.echo(f"{res.neu} Referenzkurse der EZB geladen, bis {bis}.")


@fx_app.command("show")
def show(
    waehrung: str = typer.Argument(..., help="Währung, etwa USD."),
    datum: str = typer.Option(None, "--datum", help="JJJJ-MM-TT, Standard heute."),
) -> None:
    """Referenzkurs einer Währung je Euro an einem Tag (oder dem letzten Kurstag davor)."""
    paths = Paths.default()
    tag = date.fromisoformat(datum) if datum else datetime.now(UTC).date()
    conn = connect(paths)
    try:
        kurs = store.fx_on_or_before(conn, waehrung.upper(), tag)
    finally:
        conn.close()
    if kurs is None:
        typer.echo(f"Kein Kurs für {waehrung.upper()}. Zuerst: stockagent fx update")
        raise typer.Exit(code=1)
    typer.echo(
        f"1 EUR = {formatiere(kurs.per_eur, 'kurs', 5, kurs.currency)} am {kurs.date:%d.%m.%Y} "
        f"(EZB-Referenzkurs)"
    )
