"""Befehle `stockagent universe ...` (Bauschritt 1)."""

from __future__ import annotations

import functools
import http.server
import webbrowser
from pathlib import Path

import typer
from rich.table import Table

from stockagent import tr_checks
from stockagent import universe as universe_mod
from stockagent.cli.common import app, console
from stockagent.data import store
from stockagent.data.http import FetchError
from stockagent.data.sources.deutsche_boerse import SourceFormatError
from stockagent.paths import Paths
from stockagent.report import universe_view

universe_app = typer.Typer(help="Aktienuniversum laden und anzeigen.", no_args_is_help=True)
app.add_typer(universe_app, name="universe")


@universe_app.command("update")
def universe_update(
    refresh: bool = typer.Option(
        False, "--refresh", help="Auch neu laden, wenn die Liste jung ist."
    ),
    force: bool = typer.Option(
        False, "--force", help="Große Abweichung zur letzten Liste übernehmen."
    ),
) -> None:
    """Instrumentenlisten der Deutschen Börse und LEI-Zuordnung laden."""
    paths = Paths.default()
    if not (paths.config / "sources.yaml").exists():
        typer.echo(
            "Projektordner nicht gefunden (config/sources.yaml fehlt). "
            "Im Ordner stockagent starten oder STOCKAGENT_HOME setzen."
        )
        raise typer.Exit(code=1)
    try:
        res = universe_mod.update(paths, refresh=refresh, force=force)
    except (FetchError, SourceFormatError, store.SchemaOutdated) as exc:
        typer.echo(f"Abbruch: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(res.message)
    if res.source_as_of:
        typer.echo(f"Stand der Quelle: {res.source_as_of:%d.%m.%Y}")
        typer.echo(f"Aktien: {res.stock_count} (vorher: {res.previous_count or 'keine'})")
        typer.echo(f"mit LEI: {res.with_lei}, davon Name passt nicht: {res.lei_implausible}")
        typer.echo(
            f"Land laut GLEIF: {res.country_from_gleif}, widersprüchlich: "
            f"{res.country_conflicts}, Rest nur ISIN-Land (unsicher)"
        )
        if res.pruned_raw:
            typer.echo(f"Alte GLEIF-Rohdateien gelöscht: {res.pruned_raw}")
    if res.invalid_isins:
        typer.echo(
            f"ISIN mit falscher Prüfziffer: {len(res.invalid_isins)} "
            f"(z. B. {', '.join(res.invalid_isins[:5])})"
        )
    if res.source_as_of and not res.applied:
        raise typer.Exit(code=1)


def _load_view(**filters: object) -> tuple[list[universe_view.ViewRow], universe_view.ViewMeta]:
    paths = Paths.default()
    if not paths.db.exists():
        typer.echo("Noch keine Liste geladen. Zuerst: stockagent universe update")
        raise typer.Exit(code=1)
    checks = tr_checks.load(paths.tr_checks)
    try:
        conn = store.connect(paths.db)
    except store.SchemaOutdated as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    try:
        info = universe_view.meta(conn, checks)
        if info is None:
            typer.echo("Noch keine Liste geladen. Zuerst: stockagent universe update")
            raise typer.Exit(code=1)
        return universe_view.query(conn, checks, **filters), info  # type: ignore[arg-type]
    finally:
        conn.close()


@universe_app.command("show")
def universe_show(
    search: str = typer.Option(None, "--suche", "-s", help="Name, ISIN, WKN oder Kürzel."),
    country: str = typer.Option(None, "--land", help="Land (ISO-Kürzel), z. B. DE, US."),
    tr_only: bool = typer.Option(
        False, "--nur-tr", help="Nur bei Trade Republic geprüft handelbare."
    ),
    limit: int = typer.Option(30, "--limit", "-n", help="Höchstens so viele Zeilen."),
) -> None:
    """Aktien im Terminal anzeigen."""
    rows, info = _load_view(search=search, country=country, tr_only=tr_only)
    table = Table(title=f"{len(rows)} Treffer (Stand {info.source_as_of:%d.%m.%Y})")
    table.add_column("Name", overflow="fold")
    for col in ("ISIN", "WKN", "Land", "Xetra", "Trade Republic"):
        table.add_column(col, no_wrap=True)
    for r in rows[:limit]:
        land = {"GLEIF": r.land, "widersprüchlich": f"{r.land}!"}.get(r.land_quelle, f"{r.land}*")
        table.add_row(r.name, r.isin, r.wkn, land, "ja" if r.xetra else "nein", r.tr_status)
    console.print(table)
    typer.echo(
        "Land = Hauptsitz laut GLEIF. * nur Länderkürzel der ISIN (unsicher, bei ADRs immer US). "
        "! ISIN-Land widerspricht dem Rechtssitz der LEI."
    )
    if len(rows) > limit:
        typer.echo(f"… {len(rows) - limit} weitere, mit --limit mehr anzeigen.")


@universe_app.command("html")
def universe_html(
    open_page: bool = typer.Option(False, "--open", help="Seite danach im Browser öffnen."),
) -> None:
    """Durchsuchbare Übersicht als HTML-Datei schreiben."""
    target = _write_html()
    typer.echo(f"Geschrieben: {target}")
    if open_page:
        webbrowser.open(target.as_uri())


def _write_html() -> Path:
    rows, info = _load_view()
    paths = Paths.default()
    paths.views.mkdir(parents=True, exist_ok=True)
    target = paths.views / "universum.html"
    target.write_text(universe_view.to_html(rows, info), encoding="utf-8")
    return target


@universe_app.command("serve")
def universe_serve(
    port: int = typer.Option(8765, "--port", help="Port auf 127.0.0.1."),
    open_page: bool = typer.Option(True, "--open/--no-open", help="Browser öffnen."),
) -> None:
    """Übersicht neu schreiben und unter http://127.0.0.1:<port>/ anzeigen (Strg+C beendet)."""
    target = _write_html()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(target.parent))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        url = f"http://127.0.0.1:{port}/{target.name}"
        typer.echo(f"Übersicht unter {url} (beenden mit Strg+C)")
        if open_page:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            typer.echo("Beendet.")
