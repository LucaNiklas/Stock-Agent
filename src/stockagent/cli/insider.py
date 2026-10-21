"""Befehle `stockagent insider ...` (Bauschritt 9, SPEC 3.8)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import typer
import yaml
from rich.table import Table

from stockagent import insider_update, metrics_update
from stockagent.cli.common import app, connect, console
from stockagent.core import insider
from stockagent.core.anzeige import formatiere
from stockagent.data import store
from stockagent.paths import Paths

insider_app = typer.Typer(help="Insidergeschäfte aus SEC Form 4.", no_args_is_help=True)
app.add_typer(insider_app, name="insider")


@insider_app.command("update")
def update(
    isin: Annotated[list[str], typer.Option("--isin", "-i", help="ISIN, mehrfach möglich.")],
) -> None:
    """Form-4-Meldungen der letzten Jahre laden (bereits gelesene werden übersprungen)."""
    paths = Paths.default()
    connect(paths).close()
    for e in insider_update.update(paths, isin, progress=typer.echo):
        if e.fehler:
            typer.echo(f"{e.isin}: {e.fehler}")
            continue
        typer.echo(
            f"{e.isin} {e.issuer_id}: {e.meldungen} Meldungen, davon {e.neu} neu gelesen, "
            f"{e.geschaefte} Geschäfte"
        )


@insider_app.command("show")
def show(isin: str = typer.Argument(..., help="ISIN der Aktie.")) -> None:
    """Geschäfte am offenen Markt der letzten 12 Monate mit Einordnung und Signal."""
    paths = Paths.default()
    cfg = yaml.safe_load((paths.config / "insider_thresholds.yaml").read_text("utf-8"))
    conn = connect(paths)
    try:
        iid = metrics_update.issuer_for_isin(conn, isin.upper())
        rows = store.load_insider(conn, iid) if iid else []
    finally:
        conn.close()
    if not rows:
        typer.echo(f"{isin}: keine Insidergeschäfte geladen (stockagent insider update -i {isin})")
        return
    jetzt = datetime.now(UTC)
    s = insider.signal(iid or "", rows, jetzt.date(), cfg)
    t = Table(title=f"Geschäfte am offenen Markt, letzte {cfg['signal']['fenster_tage']} Tage")
    for c in ("Tag", "Person", "Rolle", "Art", "Einordnung", "Cluster", "Beitrag"):
        t.add_column(c)
    for g in s.geschaefte:
        t.add_row(
            g.handelstag.isoformat(),
            g.person,
            g.rolle,
            "Kauf" if g.art == "buy" else "Verkauf",
            g.klasse,
            "ja" if g.cluster else "",
            formatiere(g.beitrag, "faktor", 3),
        )
    console.print(t)
    typer.echo(
        f"Säule Insider: {formatiere(s.saeule, 'faktor', 1)}"
        + (f" ({s.grund})" if s.grund else " (50 = kein Signal)")
    )
