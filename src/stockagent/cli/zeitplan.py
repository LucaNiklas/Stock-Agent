"""Befehle `stockagent zeitplan ...` (Bauschritt 12, SPEC 9.1, 15.2, ADR 0015)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from typing import Annotated

import typer

from stockagent import eskalation_issues, zeitplan
from stockagent.cli.common import app, connect
from stockagent.paths import Paths

zeitplan_app = typer.Typer(
    help="Lauf nach Zeitplan ohne Rückfragen (Profil scheduled).", no_args_is_help=True
)
app.add_typer(zeitplan_app, name="zeitplan")


@zeitplan_app.command("an")
def an() -> None:
    """Zeitplan einschalten (Lucas Entscheidung, SPEC 19 Nr. 4). Startet noch nichts."""
    zeitplan.schalten(Paths.default(), True)
    typer.echo("Zeitplan ist an. Lokal einrichten: stockagent zeitplan einrichten")


@zeitplan_app.command("aus")
def aus() -> None:
    """Zeitplan ausschalten. Ein eingerichteter Auftrag startet dann keinen Lauf mehr."""
    zeitplan.schalten(Paths.default(), False)
    typer.echo("Zeitplan ist aus.")


@zeitplan_app.command("status")
def status() -> None:
    """Schalter, letzter Lauf, Einrichtung auf diesem Mac, offene Eskalations-Issues."""
    paths = Paths.default()
    s = zeitplan.stand(paths)
    cfg = zeitplan.konfig(paths)
    typer.echo(f"Zeitplan: {'an' if s.get('aktiv') else 'aus'}")
    letzter = s.get("letzter_lauf") or "noch keiner"
    typer.echo(f"Letzter Lauf: {letzter} {s.get('letzter_lauf_id') or ''}")
    typer.echo(f"Uhrzeit laut config/run_profiles.yaml: {cfg['uhrzeit']}")
    kanaele = cfg["benachrichtigung"]["kanaele"]
    typer.echo(f"Tiefe im Profil: {cfg['profil'].get('tiefe')}, Kanäle: {kanaele}")
    eingerichtet = "eingerichtet" if zeitplan.plist_pfad().exists() else "nicht eingerichtet"
    typer.echo(f"launchd auf diesem Mac: {eingerichtet}")
    issues = eskalation_issues.zuordnung(paths)
    offen = [k for k, v in issues.items() if v.get("status") != "geschlossen"]
    typer.echo(f"Offene Eskalations-Issues: {len(offen)}")


@zeitplan_app.command("lauf")
def lauf_cmd(
    als_json: Annotated[bool, typer.Option("--json", help="Ergebnis als JSON.")] = False,
) -> None:
    """Einen Lauf nach Zeitplan jetzt ausführen (wie `run --profile scheduled --yes`)."""
    paths = Paths.default()
    connect(paths).close()
    try:
        erg = zeitplan.ausfuehren(paths, melde=lambda m: None if als_json else typer.echo(m))
    except zeitplan.ZeitplanFehler as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    if als_json:
        typer.echo(json.dumps(asdict(erg), ensure_ascii=False, indent=1, default=str))
        return
    typer.echo(f"Fertig: {erg.bewertet} bewertet, {len(erg.ereignisse)} Ereignisse.")
    for e in erg.ereignisse:
        typer.echo(f"  {e['name']}: {e['art']}, {e['text']}")
    for h in erg.hinweise:
        typer.echo(f"  Hinweis: {h}")
    typer.echo(f"Laufübersicht: runs/_laeufe/{erg.lauf_id}/report.md")


@zeitplan_app.command("einrichten")
def einrichten(
    uhrzeit: Annotated[
        str | None, typer.Option("--uhrzeit", help="HH:MM, Standard aus config/run_profiles.yaml.")
    ] = None,
    laden: Annotated[
        bool, typer.Option("--laden", help="Gleich mit launchctl aktivieren.")
    ] = False,
) -> None:
    """Täglichen Start auf diesem Mac einrichten (launchd, Rechner muss laufen). Schreibt
    ~/Library/LaunchAgents/de.stockagent.zeitplan.plist."""
    paths = Paths.default()
    uhr = uhrzeit or str(zeitplan.konfig(paths)["uhrzeit"])
    ziel = zeitplan.plist_pfad()
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(zeitplan.launchd_plist(paths, uhr))
    typer.echo(f"Geschrieben: {ziel} (täglich {uhr})")
    if laden:
        subprocess.run(["launchctl", "unload", str(ziel)], capture_output=True, check=False)
        subprocess.run(["launchctl", "load", str(ziel)], check=True)
        typer.echo("Mit launchctl geladen.")
    else:
        typer.echo(f"Aktivieren: launchctl load {ziel}")
    if not zeitplan.stand(paths).get("aktiv"):
        typer.echo("Hinweis: der Zeitplan ist noch aus (stockagent zeitplan an).")


@zeitplan_app.command("entfernen")
def entfernen() -> None:
    """Täglichen Start auf diesem Mac entfernen."""
    ziel = zeitplan.plist_pfad()
    if ziel.exists():
        subprocess.run(["launchctl", "unload", str(ziel)], capture_output=True, check=False)
        ziel.unlink()
        typer.echo(f"Entfernt: {ziel}")
    else:
        typer.echo("Nicht eingerichtet.")
