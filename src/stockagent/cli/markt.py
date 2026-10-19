"""Befehle `stockagent markt ...`: Zinsen und Damodaran-Daten (Bauschritt 4, SPEC 3.6)."""

from __future__ import annotations

from datetime import UTC, datetime

import typer

from stockagent import kapitalmarkt_update
from stockagent.cli.common import app, connect
from stockagent.core.anzeige import formatiere
from stockagent.data import store
from stockagent.data.http import FetchError
from stockagent.data.sources.damodaran import DamodaranFormatError
from stockagent.data.sources.rates import ZinsFormatError
from stockagent.data.xlsx import XlsxFormatError
from stockagent.paths import Paths

markt_app = typer.Typer(
    help="Risikofreie Zinsen und Damodaran-Daten (Beta, Risikoprämie, Ratings) laden und zeigen.",
    no_args_is_help=True,
)
app.add_typer(markt_app, name="markt")


@markt_app.command("update")
def update(
    refresh: bool = typer.Option(False, "--refresh", help="Auch laden, wenn noch aktuell."),
) -> None:
    """Zinsen (Bundesbank, US-Treasury) und Damodaran-Datensätze laden."""
    paths = Paths.default()
    connect(paths).close()
    try:
        z = kapitalmarkt_update.zinsen_update(paths, refresh=refresh)
        d = kapitalmarkt_update.damodaran_update(paths, refresh=refresh)
    except (FetchError, ZinsFormatError, DamodaranFormatError, XlsxFormatError) as exc:
        typer.echo(f"Abbruch: {exc}")
        raise typer.Exit(code=1) from exc
    for serie, (neu, bis) in z.je_serie.items():
        stand = f"{bis:%d.%m.%Y}" if bis else "-"
        zusatz = " (schon aktuell)" if serie in z.uebersprungen else f", {neu} Tageswerte geladen"
        typer.echo(f"{serie}: bis {stand}{zusatz}")
    for name, (n, ds) in d.je_datensatz.items():
        typer.echo(f"Damodaran {name}: {n} Zeilen, Stand {ds or '-'}")
    for name in d.uebersprungen:
        typer.echo(f"Damodaran {name}: schon aktuell")


@markt_app.command("show")
def show() -> None:
    """Aktueller Stand: Zinsen, Risikoprämie und Damodaran-Stände."""
    paths = Paths.default()
    heute = datetime.now(UTC).date()
    conn = connect(paths)
    try:
        for serie in ("rf_10y_EUR", "rf_10y_USD"):
            r = store.rate_on_or_before(conn, serie, heute)
            typer.echo(
                f"{serie}: "
                + (f"{formatiere(r.percent, 'kurs', 2)} % am {r.date:%d.%m.%Y}" if r else "fehlt")
            )
        e = store.erp_on_or_before(conn, heute)
        typer.echo(
            "Aktienrisikoprämie (Damodaran, implizit): "
            + (f"{formatiere(e.erp, 'percent', 2)} ab {e.month:%m.%Y}" if e else "fehlt")
        )
        for name in ("betas_us", "ratings", "wacc_us", "firms", "erp"):
            m = store.damodaran_meta(conn, name)
            typer.echo(
                f"Damodaran {name}: "
                + (f"Stand {m.stand or '-'}, geladen {m.retrieved_at:%d.%m.%Y}" if m else "fehlt")
            )
    finally:
        conn.close()
    typer.echo("Laden: stockagent markt update")


@markt_app.command("branche")
def branche(
    isin: str = typer.Argument(..., help="ISIN der Aktie."),
    name: str = typer.Argument(
        None, help="Branche genau wie bei Damodaran (Betas.html). Leer: Festlegung löschen."
    ),
) -> None:
    """Damodaran-Branche einer Aktie festlegen (für Beta und Fremdkapitalaufschlag)."""
    import yaml

    paths = Paths.default()
    datei = paths.root / "state" / "damodaran_branchen.yaml"
    daten: dict[str, str] = yaml.safe_load(datei.read_text("utf-8")) or {} if datei.exists() else {}
    isin = isin.upper()
    if name:
        conn = connect(paths)
        try:
            if store.industry_beta(conn, name) is None:
                typer.echo(
                    f"Branche {name!r} gibt es bei Damodaran nicht (stockagent markt update)."
                )
                raise typer.Exit(code=1)
        finally:
            conn.close()
        daten[isin] = name
    else:
        daten.pop(isin, None)
    datei.parent.mkdir(parents=True, exist_ok=True)
    kopf = "# Lucas Festlegungen der Damodaran-Branche je ISIN (stockagent markt branche)"
    datei.write_text(
        "\n".join([kopf, yaml.safe_dump(daten, sort_keys=True, allow_unicode=True)]), "utf-8"
    )
    typer.echo(
        f"{isin}: {name or 'Festlegung gelöscht'}. "
        f"Neu rechnen: stockagent metrics update --isin {isin}"
    )
