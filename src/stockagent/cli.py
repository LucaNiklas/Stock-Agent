"""Kommandozeile `stockagent` (SPEC 9.6)."""

from __future__ import annotations

import webbrowser
from datetime import date

import typer
from rich.console import Console
from rich.table import Table

from stockagent import __version__, tr_checks
from stockagent import universe as universe_mod
from stockagent.data import store
from stockagent.data.http import FetchError
from stockagent.data.sources.deutsche_boerse import SourceFormatError
from stockagent.paths import Paths
from stockagent.report import universe_view

app = typer.Typer(
    help="Recherche- und Bewertungssystem für bei Trade Republic handelbare Aktien.",
    no_args_is_help=True,
)
universe_app = typer.Typer(help="Aktienuniversum laden und anzeigen.", no_args_is_help=True)
app.add_typer(universe_app, name="universe")
console = Console()


def _not_yet(step: int, what: str) -> None:
    typer.echo(f"{what} ist noch nicht gebaut (Bauschritt {step}, siehe docs/spec/16-*.md).")
    raise typer.Exit(code=2)


@app.command()
def version() -> None:
    """Version anzeigen."""
    typer.echo(__version__)


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
    except (FetchError, SourceFormatError) as exc:
        typer.echo(f"Abbruch: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(res.message)
    if res.source_as_of:
        typer.echo(f"Stand der Quelle: {res.source_as_of:%d.%m.%Y}")
        typer.echo(f"Aktien: {res.stock_count} (vorher: {res.previous_count or 'keine'})")
        typer.echo(f"mit LEI: {res.with_lei}")
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
    conn = store.connect(paths.db)
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
    country: str = typer.Option(None, "--land", help="Länderkürzel der ISIN, z. B. DE, US."),
    tr_only: bool = typer.Option(
        False, "--nur-tr", help="Nur bei Trade Republic geprüft handelbare."
    ),
    limit: int = typer.Option(30, "--limit", "-n", help="Höchstens so viele Zeilen."),
) -> None:
    """Aktien im Terminal anzeigen."""
    rows, info = _load_view(search=search, country=country, tr_only=tr_only)
    table = Table(title=f"{len(rows)} Treffer (Stand {info.source_as_of:%d.%m.%Y})")
    table.add_column("Name", overflow="fold")
    for col in ("ISIN", "WKN", "Land", "Xetra", "LEI", "Trade Republic"):
        table.add_column(col, no_wrap=True)
    for r in rows[:limit]:
        table.add_row(
            r.name,
            r.isin,
            r.wkn,
            r.land,
            "ja" if r.xetra else "nein",
            "ja" if r.lei else "–",
            r.tr_status,
        )
    console.print(table)
    if len(rows) > limit:
        typer.echo(f"… {len(rows) - limit} weitere, mit --limit mehr anzeigen.")


@universe_app.command("html")
def universe_html(
    open_page: bool = typer.Option(False, "--open", help="Seite danach im Browser öffnen."),
) -> None:
    """Durchsuchbare Übersicht als HTML-Datei schreiben."""
    rows, info = _load_view()
    paths = Paths.default()
    paths.views.mkdir(parents=True, exist_ok=True)
    target = paths.views / "universum.html"
    target.write_text(universe_view.to_html(rows, info), encoding="utf-8")
    typer.echo(f"Geschrieben: {target}")
    if open_page:
        webbrowser.open(target.as_uri())


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


@app.command()
def screen() -> None:
    """Noten für alle Unternehmen berechnen, ohne Modellaufrufe."""
    _not_yet(5, "Die Notenberechnung")


@app.command()
def analyze(isin: str) -> None:
    """Finanziellen Überblick über ein Unternehmen erstellen."""
    _not_yet(6, f"Die Tiefenanalyse für {isin}")


@app.command()
def status() -> None:
    """Letzte Läufe und offene Eskalationen anzeigen."""
    _not_yet(5, "Die Statusanzeige")


@app.command()
def dashboard() -> None:
    """Dashboard bauen und öffnen."""
    _not_yet(5, "Das Dashboard")
