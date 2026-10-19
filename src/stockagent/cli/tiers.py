"""Befehle `stockagent tiers ...` (Bauschritt 5, SPEC 7.9)."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

import typer

from stockagent import tiers
from stockagent.cli.common import app, connect
from stockagent.paths import Paths

tiers_app = typer.Typer(help="Indexstufe Tier 1 bis 4 (SPEC 7.9).", no_args_is_help=True)
app.add_typer(tiers_app, name="tiers")


@tiers_app.command("import")
def importieren(
    index: Annotated[str, typer.Argument(help="Index aus config/tiers.yaml, etwa dax.")],
    datei: Annotated[Path, typer.Argument(help="Bestandsliste mit Spalte ISIN (CSV).")],
    stand: Annotated[
        str | None, typer.Option("--stand", help="Stand der Liste JJJJ-MM-TT, Standard heute.")
    ] = None,
) -> None:
    """Indexmitglieder aus einer Bestandsliste übernehmen (etwa ETF-Bestand als CSV)."""
    paths = Paths.default()
    connect(paths).close()
    tag = date.fromisoformat(stand) if stand else datetime.now(UTC).date()
    try:
        erg = tiers.importieren(paths, index, datei, tag)
    except (ValueError, OSError) as exc:
        typer.echo(f"Abbruch: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"{index}: {erg.mitglieder} Mitglieder, {erg.neu} neu, {erg.raus} ausgeschieden "
        f"(Stand {tag:%d.%m.%Y})"
    )


@tiers_app.command("show")
def show() -> None:
    """Wie viele Titel je Stufe, und welche Indizes schon Mitglieder haben."""
    paths = Paths.default()
    connect(paths).close()
    stufen = tiers.stufen_aller(paths)
    zaehler = Counter(s for s, _ in stufen.values())
    for s in (1, 2, 3, 4):
        typer.echo(f"Tier {s}: {zaehler.get(s, 0)} Titel")
    cfg = tiers.konfig(paths)
    conn = connect(paths)
    try:
        geladen = dict(
            conn.execute(
                "SELECT index_id, count(*) FROM index_members WHERE valid_to IS NULL "
                "GROUP BY index_id"
            ).fetchall()
        )
    finally:
        conn.close()
    offen = [i for i in cfg["indizes"] if i not in geladen]
    typer.echo(
        f"Indizes mit Mitgliedern: {', '.join(f'{k} ({v})' for k, v in geladen.items()) or 'keine'}"
    )
    typer.echo(f"Noch ohne Quelle: {', '.join(offen)}")
