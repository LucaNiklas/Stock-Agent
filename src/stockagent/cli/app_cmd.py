"""Befehl `stockagent app`: Dashboard als Bedienzentrale (Bauschritt 5, SPEC 13.5)."""

from __future__ import annotations

import webbrowser
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
def dashboard_cmd() -> None:
    """Wie `stockagent app`."""
    app_cmd()
