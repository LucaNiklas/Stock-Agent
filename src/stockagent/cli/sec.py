"""Befehle `stockagent sec ...` (Bauschritt 2, Abschlussdaten USA)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated

import typer
from rich.table import Table

from stockagent import metrics_update, sec_update
from stockagent.cli import metrics as metrics_cli
from stockagent.cli.common import app, connect, console
from stockagent.core import dq
from stockagent.data import concepts, quality, store
from stockagent.data.http import FetchError
from stockagent.data.sources import sec
from stockagent.paths import Paths

sec_app = typer.Typer(help="Abschlussdaten der SEC (USA) laden und anzeigen.", no_args_is_help=True)
app.add_typer(sec_app, name="sec")


@sec_app.command("update")
def update(
    isin: Annotated[
        list[str] | None,
        typer.Option("--isin", "-i", help="Nur diese ISIN, mit Abschlusswerten (mehrfach)."),
    ] = None,
    limit: int = typer.Option(
        None, "--limit", "-n", help="Abschlusswerte für die ersten N zugeordneten Firmen."
    ),
    refresh: bool = typer.Option(False, "--refresh", help="Stammdaten auch neu laden, wenn jung."),
) -> None:
    """ISIN -> CIK zuordnen, Stammdaten laden, für die Auswahl Werte und Prüfungen."""
    paths = Paths.default()
    connect(paths).close()
    try:
        res = sec_update.update(
            paths, isins=isin or None, limit=limit, refresh=refresh, progress=typer.echo
        )
    except (FetchError, sec.SecFormatError, sec.MissingUserAgent) as exc:
        typer.echo(f"Abbruch: {exc}")
        raise typer.Exit(code=1) from exc
    m = res.mapping
    typer.echo(
        f"Zuordnung ISIN -> CIK: {m.geprueft} US-ISINs, davon neu abgefragt {m.abgefragt}. "
        f"Zugeordnet {m.status['zugeordnet']}, unsicher {m.status['unsicher']}, "
        f"kein SEC-Melder {m.status['keine']}."
    )
    if isin and not (res.master_loaded or res.master_skipped or res.master_errors):
        # Mit --isin kommen die Stammdaten zusammen mit den Abschlusswerten (Review, Befund 14)
        typer.echo("Stammdaten: zusammen mit den Abschlusswerten geladen.")
    else:
        typer.echo(
            f"Stammdaten: {res.master_loaded} geladen, {res.master_skipped} noch aktuell, "
            f"{len(res.master_errors)} Fehler."
        )
    for err in res.master_errors[:5]:
        typer.echo(f"  {err}")
    for r in res.loaded:
        if r.error:
            typer.echo(f"{r.isin}: {r.error}")
        else:
            flags = ", ".join(f"{k} {v}" for k, v in sorted(r.flags.items()))
            typer.echo(f"{r.isin} {r.name}: {r.facts} Werte, Prüfungen: {flags}")
    # Abteilung Berechnung: Kennzahlen für alle Firmen mit neu geladenen Werten
    neu = [r.isin for r in res.loaded if not r.error]
    if neu:
        metrics_cli.ausgabe_lauf(metrics_update.update(paths, isins=neu))


@sec_app.command("map")
def map_isin(
    isin: str = typer.Argument(..., help="ISIN der Aktie."),
    cik: str = typer.Argument(..., help="CIK laut SEC oder 'keine' für keinen SEC-Melder."),
) -> None:
    """Zuordnung ISIN -> CIK von Hand festlegen (Vorrang vor OpenFIGI)."""
    paths = Paths.default()
    value = None if cik.lower() == "keine" else cik
    try:
        sec_update.record_override(
            sec_update.overrides_path(paths), isin.upper(), value, date.today()
        )
    except sec.SecFormatError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"{isin.upper()} -> {sec.cik10(value) if value else 'kein SEC-Melder'}. "
        f"Wirksam beim nächsten 'stockagent sec update --isin {isin.upper()}'."
    )


def _betrag(v: Decimal, unit: str, currency: str | None) -> str:
    text = f"{v:,.0f}".replace(",", ".") if unit != "per_share" else f"{v}".replace(".", ",")
    return f"{text} {currency or 'Stück' if unit == 'shares' else currency or ''}".strip()


@sec_app.command("show")
def show(isin: str = typer.Argument(..., help="ISIN der Aktie.")) -> None:
    """Stammdaten, Kernwerte des letzten Geschäftsjahres und Prüfergebnisse anzeigen."""
    paths = Paths.default()
    conn = connect(paths)
    try:
        mapping = store.load_isin_cik(conn).get(isin.upper())
        if mapping is None:
            typer.echo(f"{isin.upper()}: noch nicht zugeordnet. Zuerst: stockagent sec update")
            raise typer.Exit(code=1)
        typer.echo(f"Zuordnung: {mapping.status} über {mapping.method} ({mapping.detail})")
        if not mapping.cik:
            return
        issuer = store.load_issuer(conn, sec.issuer_id(mapping.cik))
        if issuer is None:
            typer.echo("Stammdaten fehlen. Zuerst: stockagent sec update")
            return
        typer.echo(f"{issuer.name} (CIK {issuer.cik}, LEI {issuer.lei or 'unbekannt'})")
        typer.echo(f"Branche (SIC): {issuer.sector_sic} {issuer.sic_description or ''}")
        typer.echo(f"Geschäftsadresse: {issuer.business_address}")
        typer.echo(
            f"Gründungsstaat: {issuer.state_of_incorporation}, Geschäftsjahresende "
            f"(MMTT): {issuer.fiscal_year_end}, Stand {issuer.retrieved_at:%d.%m.%Y}"
        )
        now = datetime.now(UTC)
        facts = store.pit_query(conn, as_of=now, issuer_id=issuer.issuer_id)
        if not facts:
            typer.echo(f"Noch keine Abschlusswerte. Laden: stockagent sec update --isin {isin}")
            return
        stichtage = quality.jahresstichtage(facts)
        if not stichtage:
            typer.echo("Noch kein Jahresbericht mit Abschlusswerten (etwa nach einem Börsengang).")
            return
        cmap = concepts.load(paths.config)
        table = Table(title=f"Kernwerte Geschäftsjahr bis {stichtage[0]:%d.%m.%Y}")
        for col in ("Größe", "Wert", "Konzept", "Einreichung"):
            table.add_column(col)
        for metric in cmap["kernwerte"]:
            werte = concepts.resolve(facts, cmap["us-gaap"][metric])
            treffer = [
                f
                for (s, e), f in werte.items()
                if e == stichtage[0] and (s is None or dq.periode_passt(s, e, "FY"))
            ]
            if treffer:
                f = treffer[0]
                table.add_row(
                    metric,
                    _betrag(f.value, f.unit, f.currency),
                    f.concept,
                    f"{f.form} {f.accession}",
                )
            else:
                table.add_row(metric, "unbekannt", "-", "-")
        console.print(table)
        flags = store.load_dq_flags(conn, issuer.issuer_id)
        typer.echo("Datenqualität (SPEC 3.2):")
        for flag in flags:
            wann = f" {flag.period_end:%d.%m.%Y}" if flag.period_end else ""
            typer.echo(f"  {flag.check_id} {flag.severity}{wann}: {flag.detail}")
    finally:
        conn.close()
