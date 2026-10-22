"""Befehl `stockagent app`: Dashboard als Bedienzentrale (Bauschritt 5, SPEC 13.5)."""

from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Annotated

import typer

from stockagent.cli.common import app, connect
from stockagent.dashboard import app as dashboard
from stockagent.paths import Paths


@app.command("app")
def app_cmd(
    port: Annotated[int, typer.Option("--port", help="Port auf 127.0.0.1.")] = 8765,
    oeffnen: Annotated[bool, typer.Option("--open/--no-open", help="Browser öffnen.")] = True,
) -> None:
    """Dashboard starten (nur auf diesem Rechner erreichbar). Beenden mit Strg+C."""
    paths = Paths.default()
    connect(paths).close()
    srv = dashboard.server(paths, port)
    url = f"http://127.0.0.1:{port}/"
    typer.echo(f"Dashboard läuft unter {url} (Strg+C beendet)")
    if oeffnen:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        typer.echo("Beendet.")
    finally:
        srv.server_close()


@app.command("dashboard")
def dashboard_cmd(
    html: Annotated[
        Path | None,
        typer.Option("--html", help="Statische Datei für den Lesemodus schreiben (ohne Server)."),
    ] = None,
    oeffnen: Annotated[bool, typer.Option("--open/--no-open", help="Browser öffnen.")] = True,
) -> None:
    """Wie `stockagent app`. Mit --html eine einzelne Datei zum Ansehen und Teilen (SPEC 13.3)."""
    if html is None:
        app_cmd(oeffnen=oeffnen)
        return
    from stockagent.dashboard import build

    paths = Paths.default()
    connect(paths).close()
    ziel = build.bauen(paths, html)
    typer.echo(f"Geschrieben: {ziel} (Lesemodus, ohne Server)")
    if oeffnen:
        webbrowser.open(ziel.resolve().as_uri())
