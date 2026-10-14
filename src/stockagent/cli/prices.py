"""Befehle `stockagent prices ...` (Bauschritt 4, Kurse von Yahoo, ADR 0005)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import typer

from stockagent import prices_update
from stockagent.cli.common import app, connect
from stockagent.data import store
from stockagent.data.http import FetchError
from stockagent.paths import Paths

prices_app = typer.Typer(
    help="Kurse für einzelne Titel laden und anzeigen (Yahoo, nur auf Anfrage).",
    no_args_is_help=True,
)
app.add_typer(prices_app, name="prices")


@prices_app.command("update")
def update(
    isin: Annotated[list[str], typer.Option("--isin", "-i", help="ISIN (mehrfach möglich).")],
    refresh: bool = typer.Option(False, "--refresh", help="Auch abrufen, wenn heute schon."),
) -> None:
    """Kurse der angegebenen Titel laden (beim ersten Mal 10 Jahre, danach nur Neues)."""
    paths = Paths.default()
    connect(paths).close()
    try:
        res = prices_update.update(paths, isin, refresh=refresh, progress=typer.echo)
    except FetchError as exc:
        typer.echo(f"Abbruch: {exc}")
        raise typer.Exit(code=1) from exc
    for r in res:
        if r.fehler:
            typer.echo(f"{r.isin}: kein Kurs. {r.fehler}")
            continue
        letzter = (
            f"{r.letzter.schluss} {r.waehrung or ''} am {r.letzter.datum:%d.%m.%Y}"
            if r.letzter
            else "kein Kurs"
        )
        art = "schon aktuell" if r.uebersprungen else f"{r.kurse_neu} Handelstage geladen"
        typer.echo(f"{r.isin} {r.symbol}: {art}, letzter Kurs {letzter}")
        for w in r.warnungen:
            typer.echo(f"  Warnung: {w}")


@prices_app.command("show")
def show(isin: str = typer.Argument(..., help="ISIN der Aktie.")) -> None:
    """Zuordnung, Zeitraum, letzte Kurse, Splits und Prüfungen anzeigen."""
    paths = Paths.default()
    conn = connect(paths)
    try:
        sym = store.load_price_symbol(conn, isin.upper())
        kurse = store.load_prices(conn, isin.upper())
        ereignisse = store.load_price_events(conn, isin.upper())
    finally:
        conn.close()
    if sym is None:
        typer.echo(f"{isin.upper()}: noch keine Kurse. Laden: stockagent prices update -i {isin}")
        raise typer.Exit(code=1)
    typer.echo(f"Symbol: {sym.symbol or 'keins'} ({sym.status} über {sym.method}): {sym.detail}")
    if sym.quelle_name:
        typer.echo(f"Yahoo: {sym.quelle_name}, {sym.boerse}, Währung {sym.waehrung}")
    if kurse:
        typer.echo(
            f"{len(kurse)} Handelstage vom {kurse[0].date:%d.%m.%Y} bis {kurse[-1].date:%d.%m.%Y}"
        )
        for k in kurse[-5:]:
            typer.echo(f"  {k.date:%d.%m.%Y}  {k.close} {k.currency or ''}  Volumen {k.volume}")
    splits = [e for e in ereignisse if e.kind == "split"]
    for e in splits:
        typer.echo(f"Split am {e.date:%d.%m.%Y}: {e.numerator}:{e.denominator}")
    dividenden = [e for e in ereignisse if e.kind == "dividende"]
    typer.echo(f"Dividenden: {len(dividenden)}")
    for w in sym.warnungen:
        typer.echo(f"Warnung: {w}")
    if sym.retrieved_at:
        typer.echo(f"Letzter Abruf: {sym.retrieved_at:%d.%m.%Y %H:%M} UTC, Quelle Yahoo Finance")


@prices_app.command("map")
def map_symbol(
    isin: str = typer.Argument(..., help="ISIN der Aktie."),
    symbol: str = typer.Argument(..., help="Yahoo-Symbol (etwa SAP.DE) oder 'keine'."),
) -> None:
    """Yahoo-Symbol von Hand festlegen, wenn die automatische Zuordnung danebenliegt."""
    paths = Paths.default()
    wert = None if symbol.lower() == "keine" else symbol.upper()
    prices_update.record_override(
        prices_update.overrides_path(paths), isin.upper(), wert, datetime.now(UTC).date()
    )
    typer.echo(
        f"{isin.upper()}: "
        + (f"Symbol {wert} festgelegt." if wert else "keine Kurse abrufen.")
        + " Gilt ab dem nächsten 'stockagent prices update'."
    )
