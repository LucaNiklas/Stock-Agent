"""Befehle `stockagent bewerten`, `screen`, `status` (Bauschritt 5, SPEC 6, 9.6)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

import typer
from rich.table import Table

from stockagent import bewertung
from stockagent.cli.common import app, connect, console
from stockagent.core.anzeige import formatiere
from stockagent.data import store
from stockagent.data.http import FetchError
from stockagent.paths import Paths

SAEULEN = {
    "qualitaet": "Qualität",
    "bewertung": "Bewertung",
    "stabilitaet": "Finanzielle Stabilität",
    "wachstum": "Wachstum und Trend",
    "kapitalallokation": "Kapitalallokation",
    "insider": "Insider",
    "momentum": "Momentum (Kurstrend)",
}


def zeige(g: store.GradeRow) -> None:
    zusatz = f" · {g.konfidenz or '-'} · {g.risiko or '-'}  ({g.kategorie})"
    typer.echo(f"{g.isin}: Note {g.grade}{zusatz if g.grade != 'N' else ''}")
    if g.grade == "N":
        typer.echo(f"  Nicht bewertbar: {g.grund}")
        return
    d = json.loads(g.detail_json or "{}")
    typer.echo(
        f"  Gesamtwert {formatiere(g.score, 'faktor', 1)} von 100, Scorecard {g.scorecard}, "
        f"Branche {g.branche}, Region {g.region}, Größe {g.groessenklasse}"
    )
    typer.echo(
        f"  Vergleichsgruppe: {len(d.get('gruppe', []))} Titel ({g.peer_level}), "
        f"Abdeckung {formatiere(d.get('abdeckung'), 'percent', 0)}"
    )
    if d.get("horizonte"):
        t = Table(title="Note je Anlagehorizont (gleiche Kennzahlen, Gewicht Momentum je Horizont)")
        for c in ("Horizont", "Note", "Gesamtwert", "Momentum-Anteil", "Kategorie"):
            t.add_column(c)
        for h in d["horizonte"].values():
            t.add_row(
                h["name"],
                h["note"],
                formatiere(h["score"], "faktor", 1) if h.get("score") else "-",
                formatiere(h["momentum_anteil"], "percent", 0),
                h["kategorie"],
            )
        console.print(t)
    t = Table(title="Säulen (Perzentil in der Vergleichsgruppe, 100 = beste)")
    t.add_column("Säule")
    t.add_column("Wert")
    for k, v in d.get("saeulen", {}).items():
        t.add_row(SAEULEN.get(k, k), formatiere(v, "faktor", 0) if v is not None else "-")
    console.print(t)
    t = Table(title="Kennzahlen")
    for c in ("Säule", "Kennzahl", "Statistik", "Wert", "Perzentil", "Gruppe"):
        t.add_column(c)
    for x in d.get("raenge", []):
        t.add_row(
            SAEULEN.get(x["saeule"], x["saeule"]),
            x["kennzahl"],
            x["statistik"],
            formatiere(x["wert"], "faktor", 3) if x["wert"] is not None else "fehlt",
            formatiere(x["perzentil"], "faktor", 0) if x["perzentil"] is not None else "-",
            str(x["gruppe_n"]),
        )
    console.print(t)
    if d.get("kappungen"):
        typer.echo(f"  Kappungen: {', '.join(d['kappungen'])}")
    b = d.get("bewertungsbedingung", {})
    typer.echo(
        f"  Bewertungsbedingung: {'erfüllt' if b.get('erfuellt') else 'nicht erfüllt'} "
        f"(implizites minus historisches Wachstum {formatiere(b.get('growth_gap'), 'punkte', 1)}, "
        f"Abschlag zu den Multiples der Gruppe "
        f"{formatiere(b.get('multiples_abschlag'), 'percent', 0)}"
        f"{', Kurs über Bull-Szenario' if b.get('kurs_ueber_bull') else ''})"
    )
    typer.echo(f"  Kategorie: {g.kategorie} ({d.get('kategorie_grund')})")
    for grund in d.get("konfidenz_gruende", []):
        typer.echo(f"  Konfidenz {grund}")
    typer.echo(f"  Risiko je Eingang (1 bis 5): {d.get('risiko_stufen')}")


@app.command("bewerten")
def bewerten(
    isin: str = typer.Argument(..., help="ISIN der Aktie."),
    ohne_laden: Annotated[
        bool,
        typer.Option(
            "--ohne-laden", help="Vergleichsgruppe nicht neu laden, nur vorhandene Daten nutzen."
        ),
    ] = False,
) -> None:
    """Note, Konfidenz, Risiko und Kategorie für eine Aktie gegen ihre Vergleichsgruppe."""
    paths = Paths.default()
    connect(paths).close()
    try:
        erg = bewertung.bewerten(
            paths, isin, progress=lambda m: typer.echo(m), gruppe_laden=not ohne_laden
        )
    except FetchError as exc:
        typer.echo(f"Abbruch: {exc}")
        raise typer.Exit(code=1) from exc
    if erg.grade is not None:
        zeige(erg.grade)


@app.command()
def screen(
    note: Annotated[str | None, typer.Option("--note", help="Nur diese Noten, etwa A,B.")] = None,
    horizont: Annotated[
        str | None,
        typer.Option(
            "--horizont", help="Anlagehorizont kurz, mittel oder lang (config/horizonte.yaml)."
        ),
    ] = None,
) -> None:
    """Bisher bewertete Titel mit Note, Konfidenz, Risiko und Kategorie (ohne Modellaufrufe).
    Mit --horizont Note, Gesamtwert und Kategorie dieses Horizonts."""
    paths = Paths.default()
    conn = connect(paths)
    try:
        grades = store.load_grades(conn)
        namen = dict(conn.execute("SELECT isin, name FROM listings").fetchall())
    finally:
        conn.close()
    if horizont:
        grades = [_im_horizont(g, horizont) for g in grades]
    if note:
        erlaubt = {n.strip().upper() for n in note.split(",")}
        grades = [g for g in grades if g.grade in erlaubt]
    t = Table(
        title=f"Bewertete Titel: {len(grades)}" + (f" (Horizont {horizont})" if horizont else "")
    )
    for c in ("ISIN", "Name", "Note", "Wert", "K", "R", "Kategorie", "Branche", "Stand"):
        t.add_column(c)
    for g in sorted(grades, key=lambda g: (g.grade, -(g.score or 0))):
        t.add_row(
            g.isin,
            str(namen.get(g.isin, ""))[:28],
            g.grade,
            formatiere(g.score, "faktor", 0) if g.score is not None else "-",
            g.konfidenz or "-",
            g.risiko or "-",
            g.kategorie or "-",
            (g.branche or "-")[:30],
            f"{g.as_of:%d.%m.%Y}",
        )
    console.print(t)
    typer.echo("Einzelner Titel: stockagent bewerten <ISIN>")


def _im_horizont(g: store.GradeRow, horizont: str) -> store.GradeRow:
    """Note, Gesamtwert und Kategorie eines Horizonts. Ältere Bewertungen ohne Horizonte
    bleiben unverändert."""
    h = (json.loads(g.detail_json or "{}").get("horizonte") or {}).get(horizont)
    if not h:
        return g
    return replace(
        g,
        grade=h["note"],
        score=Decimal(h["score"]) if h.get("score") else None,
        kategorie=h["kategorie"],
    )


@app.command()
def status() -> None:
    """Datenstand und offene Hinweise an die Agenten."""
    paths = Paths.default()
    conn = connect(paths)
    try:
        n_grades = conn.execute("SELECT count(*) FROM grades").fetchone()
        n_snap = conn.execute(
            "SELECT count(DISTINCT snapshot_date) FROM grade_snapshots"
        ).fetchone()
        n_hinweise = conn.execute("SELECT count(*) FROM hinweise WHERE status = 'offen'").fetchone()
        n_kurse = conn.execute("SELECT count(DISTINCT isin) FROM prices").fetchone()
        n_kz = conn.execute("SELECT count(DISTINCT issuer_id) FROM metric_runs").fetchone()
    finally:
        conn.close()
    heute = datetime.now(UTC).date()
    typer.echo(f"Stand {heute:%d.%m.%Y}")
    typer.echo(f"  Bewertete Titel: {n_grades[0] if n_grades else 0}")
    typer.echo(f"  Tage mit eingefrorenen Noten (Notenkontrolle): {n_snap[0] if n_snap else 0}")
    typer.echo(f"  Titel mit Kursen: {n_kurse[0] if n_kurse else 0}")
    typer.echo(f"  Emittenten mit Kennzahlen: {n_kz[0] if n_kz else 0}")
    typer.echo(f"  Offene Hinweise an die Agenten: {n_hinweise[0] if n_hinweise else 0}")
