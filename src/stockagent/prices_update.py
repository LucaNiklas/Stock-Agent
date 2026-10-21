"""Kurse laden (Bauschritt 4, Abteilung Recherche, ADR 0005).

Nur für angefragte Titel und ihre Vergleichsgruppe, nie für das ganze Universum. Ablauf je ISIN:

1. Yahoo-Symbol bestimmen. Lucas Zuordnung in `state/price_symbols.yaml` hat Vorrang. Sonst die
   Notierungen laut OpenFIGI in der Reihenfolge Heimatbörse, USA, Xetra, Frankfurt. Ein Symbol
   gilt als zugeordnet, wenn Yahoo eine Aktie liefert und der Name zum Börsennamen passt.
   Passt keiner, bleibt der Titel ohne Kurs (unsicher, mit Grund).
2. Kurse abrufen: beim ersten Mal 10 Jahre, danach nur die letzten Monate, und nur wenn der
   letzte Abruf älter als ein Tag ist.
3. Prüfen: Kurse positiv, Währung gesetzt, letzter Kurs nicht veraltet. Speichern mit Rohdatei.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from stockagent.core import dq
from stockagent.core.identifiers import names_plausibly_match
from stockagent.data import store
from stockagent.data.http import FetchError, fetch
from stockagent.data.sources import openfigi, yahoo
from stockagent.paths import Paths

Progress = Callable[[str], None]
QUELLE = "yahoo"


def _noop(_: str) -> None:
    pass


# ------------------------------------------------------------------ Lucas Zuordnungen


def overrides_path(paths: Paths) -> Path:
    return paths.root / "state" / "price_symbols.yaml"


def load_overrides(path: Path) -> dict[str, str | None]:
    """ISIN -> Yahoo-Symbol oder None für "keinen Kurs abrufen"."""
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text("utf-8")) or {}
    return {isin: (v.get("symbol") or None) for isin, v in data.items()}


def record_override(path: Path, isin: str, symbol: str | None, on: date) -> None:
    data: dict[str, Any] = {}
    if path.exists():
        data = yaml.safe_load(path.read_text("utf-8")) or {}
    data[isin] = {"symbol": symbol, "geprueft_am": on.isoformat()}
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Lucas Zuordnungen ISIN -> Yahoo-Symbol (ADR 0005). Gepflegt mit\n"
        "# `stockagent prices map <ISIN> <SYMBOL>|keine`. Vorrang vor OpenFIGI.\n"
    )
    path.write_text(header + yaml.safe_dump(data, sort_keys=True), encoding="utf-8")


# ------------------------------------------------------------------ Prüfung


def abgeschlossen(chart: yahoo.Chart, jetzt: datetime) -> list[yahoo.Tageskurs]:
    """Nur Tage mit Schlusskurs: Der laufende Handelstag fehlt bis zum Handelsende."""
    if chart.handelsende is None or jetzt >= chart.handelsende:
        return chart.kurse
    laufend = chart.handelsende.astimezone(ZoneInfo(chart.zeitzone)).date()
    return [k for k in chart.kurse if k.datum < laufend]


def pruefe(chart: yahoo.Chart, heute: date, veraltet_tage: int) -> list[str]:
    warnungen = []
    if not chart.kurse:
        return ["keine Kurse im Abruf"]
    if not chart.waehrung:
        warnungen.append("Währung fehlt")
    nicht_positiv = [k.datum for k in chart.kurse if k.schluss <= 0]
    if nicht_positiv:
        warnungen.append(f"Schlusskurs null oder negativ an {len(nicht_positiv)} Tagen")
    if dq.kurs_veraltet(chart.kurse[-1].datum, heute, veraltet_tage):
        warnungen.append(f"letzter Kurs vom {chart.kurse[-1].datum:%d.%m.%Y}, Handel ausgesetzt?")
    return warnungen


def _passt(chart: yahoo.Chart, boersenname: str, figi_name: str | None) -> tuple[bool, str]:
    if chart.art and chart.art != "EQUITY":
        return False, f"Yahoo meldet {chart.art}, keine Aktie"
    if not chart.kurse:
        return False, "keine Kurse"
    name = chart.name or ""
    if names_plausibly_match(boersenname, name) or (
        figi_name is not None and names_plausibly_match(figi_name, name)
    ):
        return True, f"Name passt: {name}"
    return False, f"Name passt nicht: Börse '{boersenname}', Yahoo '{name}'"


# ------------------------------------------------------------------ Ablauf


@dataclass
class KursErgebnis:
    isin: str
    symbol: str | None = None
    status: str = "keine"
    kurse_neu: int = 0
    letzter: yahoo.Tageskurs | None = None
    waehrung: str | None = None
    warnungen: list[str] = field(default_factory=list)
    fehler: str | None = None
    uebersprungen: bool = False
    laufend: yahoo.Tageskurs | None = None  # Kurs des laufenden Handelstags, nicht gespeichert


class _Lauf:
    def __init__(
        self,
        paths: Paths,
        cfg: dict[str, Any],
        yahoo_client: yahoo.YahooClient,
        figi: openfigi.OpenFigiClient,
        now: datetime,
        refresh: bool,
    ) -> None:
        self.paths = paths
        self.cfg = cfg
        self.yahoo = yahoo_client
        self.figi = figi
        self.now = now
        self.refresh = refresh
        self.overrides = load_overrides(overrides_path(paths))

    def zeitraum(self, vorhanden: bool) -> str:
        return str(self.cfg["nachabruf"] if vorhanden else self.cfg["erstabruf"])

    def zuordnen(
        self, conn: Any, isin: str, name: str, land: str | None
    ) -> tuple[store.PriceSymbol, yahoo.Abruf | None]:
        """Symbol bestimmen. Liefert den ersten Abruf mit, damit nicht doppelt abgerufen wird."""
        jetzt = self.now
        if isin in self.overrides:
            sym = self.overrides[isin]
            if sym is None:
                return store.PriceSymbol(
                    isin,
                    None,
                    None,
                    "manuell",
                    "keine",
                    "Lucas Vorgabe: kein Kurs",
                    None,
                    None,
                    None,
                    (),
                    jetzt,
                    None,
                ), None
            return store.PriceSymbol(
                isin,
                sym,
                None,
                "manuell",
                "zugeordnet",
                "Lucas Vorgabe",
                None,
                None,
                None,
                (),
                jetzt,
                None,
            ), None
        bekannt = store.load_price_symbol(conn, isin)
        if bekannt and bekannt.status == "zugeordnet" and bekannt.method == "openfigi":
            return bekannt, None
        notierungen = self.figi.listings([isin]).get(isin, [])
        kandidaten = yahoo.kandidaten(notierungen, land, self.cfg)
        if not kandidaten:
            return store.PriceSymbol(
                isin,
                None,
                None,
                "openfigi",
                "keine",
                "OpenFIGI kennt keine Notierung an einer Börse, die Yahoo abdeckt",
                None,
                None,
                None,
                (),
                jetzt,
                None,
            ), None
        figi_name = next((n.name for n in notierungen if n.name), None)
        gruende = []
        vorhanden = bool(store.load_prices(conn, isin))
        for code, sym in kandidaten:
            try:
                abruf = self.yahoo.chart(sym, self.zeitraum(vorhanden))
            except yahoo.YahooError as exc:
                gruende.append(f"{sym}: {exc}")
                continue
            ok, grund = _passt(abruf.chart, name, figi_name)
            if ok:
                return store.PriceSymbol(
                    isin,
                    sym,
                    code,
                    "openfigi",
                    "zugeordnet",
                    grund,
                    abruf.chart.name,
                    abruf.chart.waehrung,
                    abruf.chart.boerse,
                    (),
                    jetzt,
                    None,
                ), abruf
            gruende.append(f"{sym}: {grund}")
        return store.PriceSymbol(
            isin,
            None,
            None,
            "openfigi",
            "unsicher",
            "; ".join(gruende),
            None,
            None,
            None,
            (),
            jetzt,
            None,
        ), None

    def aktuell(self, bekannt: store.PriceSymbol | None) -> bool:
        if self.refresh or bekannt is None or bekannt.retrieved_at is None:
            return False
        return dq.juenger_als(
            bekannt.retrieved_at.date(), self.now.date(), int(self.cfg["aktuell_tage"])
        )

    def titel(self, conn: Any, isin: str) -> KursErgebnis:
        ergebnis = KursErgebnis(isin)
        info = store.listing_info(conn, isin)
        if info is None:
            ergebnis.fehler = "nicht im Universum"
            return ergebnis
        name, land = info
        if store.listing_is_receipt(conn, isin):
            # Hinterlegungsscheine (ADRs) handeln in den USA, die Heimatbörse der Firma führt die
            # Stammaktie. Sonst wählt die Zuordnung etwa die Londoner Zeile eines ADRs (BP, Diageo)
            land = "US"
        bekannt = store.load_price_symbol(conn, isin)
        if bekannt and bekannt.status == "zugeordnet" and self.aktuell(bekannt):
            ergebnis.symbol, ergebnis.status, ergebnis.uebersprungen = (
                bekannt.symbol,
                bekannt.status,
                True,
            )
            kurse = store.load_prices(conn, isin)
            if kurse:
                k = kurse[-1]
                ergebnis.letzter = yahoo.Tageskurs(k.date, k.close, k.adj_close, k.volume)
                ergebnis.waehrung = k.currency
            return ergebnis
        zuordnung, abruf = self.zuordnen(conn, isin, name, land)
        ergebnis.symbol, ergebnis.status = zuordnung.symbol, zuordnung.status
        if zuordnung.symbol is None:
            store.save_price_symbol(conn, zuordnung)
            ergebnis.fehler = zuordnung.detail
            return ergebnis
        if abruf is None:
            vorhanden = bool(store.load_prices(conn, isin))
            try:
                abruf = self.yahoo.chart(zuordnung.symbol, self.zeitraum(vorhanden))
            except yahoo.YahooError as exc:
                ergebnis.fehler = str(exc)
                store.save_price_symbol(conn, zuordnung)
                return ergebnis
        chart = abruf.chart
        warnungen = pruefe(chart, self.now.date(), int(self.cfg["veraltet_tage"]))
        tage = abgeschlossen(chart, self.now)
        zeilen = [
            store.PriceRow(
                isin,
                k.datum,
                k.schluss,
                k.schluss_bereinigt,
                k.volumen,
                chart.waehrung,
                zuordnung.symbol,
                QUELLE,
            )
            for k in tage
            if k.schluss > 0
        ]
        ereignisse = [
            store.PriceEvent(
                isin,
                e.datum,
                e.art,
                e.wert,
                e.zaehler,
                e.nenner,
                chart.waehrung,
                zuordnung.symbol,
                QUELLE,
            )
            for e in chart.ereignisse
        ]
        store.save_prices(conn, zeilen, ereignisse, abruf.raw.sha256, self.now)
        if len(tage) < len(chart.kurse):
            store.delete_prices_from(conn, isin, chart.kurse[-1].datum, QUELLE)
        store.save_price_symbol(
            conn,
            store.PriceSymbol(
                isin,
                zuordnung.symbol,
                zuordnung.exch_code,
                zuordnung.method,
                zuordnung.status,
                zuordnung.detail,
                chart.name,
                chart.waehrung,
                chart.boerse,
                tuple(warnungen),
                self.now,
                self.now,
            ),
        )
        ergebnis.kurse_neu = len(zeilen)
        ergebnis.letzter = tage[-1] if tage else None
        if len(tage) < len(chart.kurse):
            ergebnis.laufend = chart.kurse[-1]
        ergebnis.waehrung = chart.waehrung
        ergebnis.warnungen = warnungen
        return ergebnis


def update(
    paths: Paths,
    isins: list[str],
    *,
    refresh: bool = False,
    fetcher: Callable[..., bytes] = fetch,
    sleep: Callable[[float], None] = time.sleep,
    now: datetime | None = None,
    progress: Progress = _noop,
) -> list[KursErgebnis]:
    """Kurse für die angefragten ISINs laden und speichern."""
    now = now or datetime.now(UTC)
    cfg = yaml.safe_load((paths.config / "sources.yaml").read_text("utf-8"))
    if not cfg["yahoo"].get("enabled"):
        return [KursErgebnis(i.upper(), fehler="Kursquelle Yahoo ist ausgeschaltet") for i in isins]
    client = yahoo.YahooClient(
        cfg["yahoo"], cfg["user_agent"], paths.raw, fetcher=fetcher, sleep=sleep, now=lambda: now
    )
    figi = openfigi.OpenFigiClient(
        cfg["openfigi"],
        cfg["user_agent"],
        paths.raw,
        fetcher=fetcher,
        sleep=sleep,
        now=lambda: now,
    )
    lauf = _Lauf(paths, cfg["yahoo"], client, figi, now, refresh)
    conn = store.connect(paths.db)
    out = []
    try:
        for isin in dict.fromkeys(i.upper() for i in isins):
            progress(f"Kurse: {isin}")
            try:
                out.append(lauf.titel(conn, isin))
            except (FetchError, yahoo.YahooFormatError) as exc:
                out.append(KursErgebnis(isin, fehler=str(exc)))
    finally:
        conn.close()
    return out
