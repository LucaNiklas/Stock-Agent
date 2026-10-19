"""Befehle `stockagent metrics ...` (Bauschritt 3, Abteilung Berechnung)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Annotated, Any

import typer
import yaml
from rich.table import Table

from stockagent import metrics_update
from stockagent.cli.common import app, connect, console
from stockagent.core.anzeige import formatiere
from stockagent.data import store
from stockagent.paths import Paths

metrics_app = typer.Typer(
    help="Kennzahlen mit Rechenweg rechnen und anzeigen.", no_args_is_help=True
)
app.add_typer(metrics_app, name="metrics")


def ausgabe_lauf(ergebnisse: list[metrics_update.Ergebnis]) -> None:
    for e in ergebnisse:
        if e.fehler or e.rechnung is None:
            typer.echo(f"{e.isin}: {e.fehler}")
            continue
        r = e.rechnung
        z = r.zaehlung()
        typer.echo(
            f"{e.isin}: Geschäftsjahr bis {r.stichtag:%d.%m.%Y}: {z['berechnet']} berechnet, "
            f"{z['fehlt']} ohne Eingabe, {z['gestoppt']} durch Prüfpunkt gestoppt. "
            f"{len(r.hinweise)} Hinweise an die Agenten."
        )


@metrics_app.command("update")
def update(
    isin: Annotated[
        list[str] | None,
        typer.Option("--isin", "-i", help="Nur diese ISIN (mehrfach). Ohne: alle mit Werten."),
    ] = None,
    as_of: Annotated[
        str | None,
        typer.Option("--as-of", help="Datenstand JJJJ-MM-TT (Standard: jetzt)."),
    ] = None,
) -> None:
    """Kennzahlen, Trends und Hinweise rechnen und speichern."""
    paths = Paths.default()
    connect(paths).close()
    stand = datetime.fromisoformat(as_of).replace(tzinfo=UTC) if as_of else None
    ausgabe_lauf(metrics_update.update(paths, isins=isin, as_of=stand, progress=typer.echo))


def _definitionen(paths: Paths) -> dict[str, dict[str, Any]]:
    cfg = yaml.safe_load((paths.config / "metrics.yaml").read_text("utf-8"))
    return {m["id"]: m for m in cfg["metrics"]}


def _rechenweg(trace: dict[str, Any], grund: str | None, vermerke: tuple[str, ...]) -> None:
    typer.echo(
        f"Rechenweg {trace['name']} {trace['version']}, {trace['subjekt']} {trace['periode']}"
    )
    for s in trace["schritte"]:
        typer.echo(f"  {s['name']} = {s['formel']} = {s['ergebnis']}")
        for k, v in s["eingaben"].items():
            text = (
                f"{v['wert']} {v.get('waehrung') or ''} ({v['quelle']})"
                if isinstance(v, dict)
                else v
            )
            typer.echo(f"      {k}: {text}")
    for p in trace["pruefungen"]:
        typer.echo(
            f"  {p['cp_id']} {'ok' if p['bestanden'] else 'VERLETZT'} ({p['stufe']}): {p['text']}"
        )
    for v in vermerke:
        typer.echo(f"  Vermerk: {v}")
    if grund:
        typer.echo(f"Ergebnis unbekannt: {grund}")


def _waehrung(rows: list[store.MetricRow]) -> str | None:
    """Berichtswährung aus den Eingaben eines Rechenwegs (alle Eingaben haben dieselbe, CP-01)."""
    for r in rows:
        if r.calc_trace_json is None:
            continue
        for s in json.loads(r.calc_trace_json)["schritte"]:
            for v in s["eingaben"].values():
                if isinstance(v, dict) and v.get("waehrung"):
                    return str(v["waehrung"])
    return None


@metrics_app.command("show")
def show(
    isin: str = typer.Argument(..., help="ISIN der Aktie."),
    rechenweg: Annotated[
        str | None,
        typer.Option("--rechenweg", "-r", help="Rechenweg dieser Kennzahl zeigen (etwa roic)."),
    ] = None,
    jahr: Annotated[
        int | None,
        typer.Option("--jahr", "-j", help="Mit --rechenweg: Geschäftsjahr (Jahr des Endes)."),
    ] = None,
    trend: Annotated[
        str | None,
        typer.Option(
            "--trend", "-t", help="Mit --rechenweg: Trend zeigen (etwa steigung, plausibilitaet)."
        ),
    ] = None,
    aktuell: Annotated[
        bool,
        typer.Option("--aktuell", "-a", help="Mit --rechenweg: Bewertung mit letztem Kurs zeigen."),
    ] = False,
) -> None:
    """Kennzahlen des letzten Geschäftsjahres mit Trend, Bewertung und Hinweisen anzeigen."""
    paths = Paths.default()
    conn = connect(paths)
    try:
        issuer = metrics_update.issuer_for_isin(conn, isin)
        lauf = store.load_metric_run(conn, issuer) if issuer else None
        if issuer is None or lauf is None:
            typer.echo(f"{isin.upper()}: noch keine Kennzahlen. Zuerst: stockagent metrics update")
            raise typer.Exit(code=1)
        _, as_of, stichtag, version = lauf
        rows = [r for r in store.load_metrics(conn, issuer) if r.period_end == stichtag]
        hinweise = store.load_hinweise(conn, issuer)
    finally:
        conn.close()
    je = {(r.metric_id, r.statistik): r for r in rows}
    if rechenweg:
        if (rechenweg, "wert") not in je:
            typer.echo(f"Kennzahl {rechenweg} unbekannt.")
            raise typer.Exit(code=1)
        if trend:
            conn = connect(paths)
            try:
                cfg = metrics_update.Konfiguration.laden(paths.config)
                erg = metrics_update.nachrechnen_trend(
                    conn, issuer, as_of.replace(tzinfo=UTC), rechenweg, trend, cfg
                )
            finally:
                conn.close()
            if erg is None:
                typer.echo(f"Trend {trend} für {rechenweg} nicht vorhanden.")
                raise typer.Exit(code=1)
            typer.echo(f"Nachgerechnet zum Datenstand {as_of:%d.%m.%Y}")
            _rechenweg(erg.rechenweg, erg.grund, erg.vermerke)
            return
        if aktuell:
            if (rechenweg, "aktuell") not in je:
                typer.echo(f"Für {rechenweg} gibt es keine Bewertung mit aktuellem Kurs.")
                raise typer.Exit(code=1)
            row = je[(rechenweg, "aktuell")]
            trace = json.loads(row.calc_trace_json) if row.calc_trace_json else {}
            _rechenweg(trace, row.grund, row.vermerke)
            return
        if jahr is None or stichtag is None or jahr == stichtag.year:
            row = je[(rechenweg, "wert")]
            trace = json.loads(row.calc_trace_json) if row.calc_trace_json else {}
            _rechenweg(trace, row.grund, row.vermerke)
            return
        conn = connect(paths)
        try:
            cfg = metrics_update.Konfiguration.laden(paths.config)
            stand = as_of.replace(tzinfo=UTC)
            erg = metrics_update.nachrechnen(conn, issuer, stand, rechenweg, jahr, cfg)
        finally:
            conn.close()
        if erg is None:
            typer.echo(f"Geschäftsjahr {jahr} nicht im Datenstand.")
            raise typer.Exit(code=1)
        typer.echo(
            f"Nachgerechnet zum Datenstand {as_of:%d.%m.%Y} (Vorjahre speichern nur den Wert)"
        )
        _rechenweg(erg.rechenweg, erg.grund, erg.vermerke)
        return
    defs = _definitionen(paths)
    geld = _waehrung(rows)
    table = Table(
        title=f"Kennzahlen Geschäftsjahr bis {stichtag:%d.%m.%Y} "
        f"(Datenstand {as_of:%d.%m.%Y}, Methodik {version})"
    )
    for col in ("Kennzahl", "Wert", "Vorjahr", "Trend je Jahr", "Anmerkung"):
        table.add_column(col)
    for metric_id, d in defs.items():
        if d.get("kurs"):
            continue  # eigene Tabelle unten
        anz, st = d["rundung"]["anzeige"], int(d["rundung"]["nachkommastellen"])
        wert = je.get((metric_id, "wert"))
        vj = je.get((metric_id, "veraenderung_vj"))
        steigung = je.get((metric_id, "steigung"))
        # Quoten ändern sich in Prozentpunkten, Beträge relativ (core/trends.py)
        anz_trend = "punkte" if anz == "percent" else anz
        if vj is None or vj.value is None:
            vj_text = "-"
        elif d["einheit"] in ("monetary", "per_share", "shares"):
            vj_text = formatiere(vj.value, "percent", 1)
        else:
            vj_text = formatiere(vj.value, anz_trend, st, geld)
        trend_text = (
            "-"
            if steigung is None or steigung.value is None
            else formatiere(steigung.value, anz_trend, st, geld)
        )
        notiz = ""
        if wert is not None and wert.grund:
            notiz = wert.grund
        elif wert is not None and wert.vermerke:
            notiz = "abgeleitet: " + wert.vermerke[0].split(": ", 1)[-1]
        plaus = je.get((metric_id, "plausibilitaet"))
        if plaus is not None and plaus.warnungen:
            notiz = "Sprung gegen die eigene Historie (CP-05)"
        table.add_row(
            d["name"],
            formatiere(wert.value if wert else None, anz, st, geld),
            vj_text,
            trend_text,
            notiz[:70],
        )
    console.print(table)
    _bewertung(defs, je, stichtag, geld)
    typer.echo(f"Offene Hinweise an die Agenten: {len(hinweise)}")
    for h in hinweise:
        typer.echo(
            f"  {h.regel} an {h.an_agent} ({h.abteilung}) {h.metric_id or ''}: {h.detail[:100]}"
        )
    typer.echo("Rechenweg einer Kennzahl: stockagent metrics show <ISIN> --rechenweg <id>")
    typer.echo("Mit aktuellem Kurs: stockagent metrics show <ISIN> --rechenweg pe --aktuell")


def _kurstag(row: store.MetricRow | None) -> str | None:
    """Handelstag des Kurses aus dem Rechenweg (Quelle „Yahoo SYM Schlusskurs JJJJ-MM-TT“)."""
    if row is None or not row.calc_trace_json:
        return None
    for s in json.loads(row.calc_trace_json)["schritte"]:
        for e in s["eingaben"].values():
            if isinstance(e, dict) and "Schlusskurs" in str(e.get("quelle", "")):
                tag = date.fromisoformat(str(e["quelle"]).rsplit(" ", 1)[-1])
                return f"{tag:%d.%m.%Y}"
    return None


def _bewertung(
    defs: dict[str, dict[str, Any]],
    je: dict[tuple[str, str], store.MetricRow],
    stichtag: Any,
    geld: str | None,
) -> None:
    bewertung = {m: d for m, d in defs.items() if d.get("kurs")}
    if not bewertung:
        return
    tag = _kurstag(je.get(("pe", "aktuell"))) or _kurstag(je.get(("market_cap", "aktuell")))
    table = Table(
        title=f"Bewertung mit Börsenkurs (Kurs am Geschäftsjahresende {stichtag:%d.%m.%Y} "
        f"und aktuell{f' vom {tag}' if tag else ''})"
    )
    for col in ("Kennzahl", "GJ-Ende", "Aktuell", "Rang in 10 Jahren", "Anmerkung"):
        table.add_column(col)
    for metric_id, d in bewertung.items():
        anz, st = d["rundung"]["anzeige"], int(d["rundung"]["nachkommastellen"])
        wert, jetzt = je.get((metric_id, "wert")), je.get((metric_id, "aktuell"))
        p = je.get((metric_id, "perzentil_historie"))
        rang = "-" if p is None or p.value is None else formatiere(p.value, "percent", 0)
        notiz = next((r.grund for r in (jetzt, wert, p) if r is not None and r.grund), "")
        table.add_row(
            d["name"],
            formatiere(wert.value if wert else None, anz, st, geld),
            formatiere(jetzt.value if jetzt else None, anz, st, geld),
            rang,
            (notiz or "")[:70],
        )
    console.print(table)
    typer.echo(
        "Rang: Anteil der Geschäftsjahre, in denen der Wert höchstens so hoch war wie aktuell "
        "(100 % = so hoch wie nie)."
    )
