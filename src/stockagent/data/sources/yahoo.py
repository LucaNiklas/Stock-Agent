"""Kurse von Yahoo Finance (ADR 0005, SPEC 7.3).

Yahoo hat keine offizielle Schnittstelle. Genutzt wird die Chart-Adresse, die auch die
Bibliothek yfinance verwendet, aber mit unserem eigenen User-Agent: Wir geben uns nicht als
Browser aus und umgehen keinen Schutz. Lehnt Yahoo das ab, bricht der Abruf mit Grund ab.
Laut Yahoo nur für persönliche Zwecke, deshalb nur für angefragte Titel und ihre
Vergleichsgruppe, langsam und mit Pause (`config/sources.yaml`, Abschnitt `yahoo`).

Yahoo liefert Kurse als Gleitkommazahlen mit Rundungsrauschen (345.79998779296875 statt 345.80).
Gespeichert wird der Wert wie geliefert, gerundet wird erst bei Anzeige und Rechnung in `core/`.
Während des Handels enthält die Antwort für den laufenden Tag einen laufenden Kurs. Den
erkennt `handelsende` (reguläres Handelsende laut Yahoo), `prices_update.py` speichert ihn nicht.

Die Antwort enthält je Handelstag Schlusskurs (um Splits bereinigt), Schlusskurs bereinigt um
Splits und Dividenden, Volumen, dazu Split- und Dividendenereignisse. Jede Antwort landet
unverändert in `data/raw/`. Zahlen werden als Text übernommen, wie geliefert (`Decimal`), ohne
Rundung und ohne Umrechnung. Unterwährungen wie GBp (Pence) bleiben so stehen und werden erst
in `core/fx.py` umgerechnet.
"""

from __future__ import annotations

import json
import time
import urllib.parse
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from stockagent.data import rawstore
from stockagent.data.http import NotFound, fetch
from stockagent.data.sources.openfigi import Listing


class YahooError(RuntimeError):
    """Yahoo kennt das Symbol nicht oder liefert keine Kurse."""


class YahooFormatError(ValueError):
    """Die Antwort hat nicht die erwartete Form (Yahoo hat die Schnittstelle geändert)."""


@dataclass(frozen=True)
class Tageskurs:
    datum: date  # Handelstag an der Börse (Zeitzone der Börse)
    schluss: Decimal  # um Splits bereinigt
    schluss_bereinigt: Decimal | None  # um Splits und Dividenden bereinigt
    volumen: int | None


@dataclass(frozen=True)
class Ereignis:
    datum: date
    art: str  # split oder dividende
    wert: Decimal | None = None  # Dividende je Aktie
    zaehler: Decimal | None = None  # Split 4:1: Zähler 4, Nenner 1. Den Faktor rechnet core/
    nenner: Decimal | None = None


@dataclass(frozen=True)
class Chart:
    symbol: str
    waehrung: str | None
    boerse: str | None
    art: str | None  # instrumentType, etwa EQUITY
    name: str | None
    zeitzone: str
    kurse: list[Tageskurs]
    ereignisse: list[Ereignis] = field(default_factory=list)
    # Ende des regulären Handels am laufenden oder letzten Handelstag (UTC). Bis dahin ist der
    # Kurs des Tages ein laufender Kurs und noch kein Schlusskurs.
    handelsende: datetime | None = None


def symbol(listing: Listing, endungen: dict[str, str]) -> str | None:
    """Yahoo-Symbol aus einer OpenFIGI-Notierung, None für unbekannte Börsen."""
    if listing.exch_code not in endungen:
        return None
    ticker = listing.ticker.strip().upper().rstrip("/.")
    ticker = ticker.replace("/", "-").replace(" ", "-")
    if listing.exch_code == "HK" and ticker.isdigit():
        ticker = ticker.zfill(4)  # Hongkong: 700 -> 0700.HK
    return f"{ticker}{endungen[listing.exch_code]}"


def kandidaten(
    listings: Iterable[Listing], land: str | None, cfg: dict[str, Any]
) -> list[tuple[str, str]]:
    """(Börsenkürzel, Yahoo-Symbol) in der Reihenfolge Heimatbörse, USA, Xetra, Frankfurt."""
    reihenfolge = [*cfg["heimatboerse"].get(land or "", []), *cfg["rueckfall"]]
    je_boerse: dict[str, str] = {}
    for listing in listings:
        s = symbol(listing, cfg["endungen"])
        if s and listing.exch_code not in je_boerse:
            je_boerse[listing.exch_code] = s
    out: list[tuple[str, str]] = []
    for code in reihenfolge:
        if code in je_boerse and (code, je_boerse[code]) not in out:
            out.append((code, je_boerse[code]))
    return out


def _datum(ts: int, zone: ZoneInfo) -> date:
    return datetime.fromtimestamp(ts, zone).date()


def parse_chart(raw: bytes) -> Chart:
    try:
        body = json.loads(raw, parse_float=Decimal)
        chart = body["chart"]
    except (ValueError, KeyError, TypeError) as exc:
        raise YahooFormatError("Antwort ist kein Chart von Yahoo") from exc
    if chart.get("error"):
        err = chart["error"]
        raise YahooError(f"Yahoo: {err.get('description') or err.get('code') or err}")
    results = chart.get("result") or []
    if not results:
        raise YahooError("Yahoo: keine Daten")
    res = results[0]
    try:
        meta = res["meta"]
        zeitzone = str(meta.get("exchangeTimezoneName") or "UTC")
        zone = ZoneInfo(zeitzone)
        stempel = res.get("timestamp") or []
        quote = (res.get("indicators", {}).get("quote") or [{}])[0]
        adj = (res.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose") or []
        schluss = quote.get("close") or []
        volumen = quote.get("volume") or []
    except (KeyError, TypeError, IndexError) as exc:
        raise YahooFormatError("Chart von Yahoo unvollständig") from exc
    if len(schluss) != len(stempel):
        raise YahooFormatError("Anzahl Kurse passt nicht zur Anzahl Handelstage")
    kurse = []
    for i, ts in enumerate(stempel):
        if schluss[i] is None:
            continue  # Yahoo füllt Tage ohne Handel mit null
        kurse.append(
            Tageskurs(
                _datum(int(ts), zone),
                Decimal(schluss[i]),
                Decimal(adj[i]) if i < len(adj) and adj[i] is not None else None,
                int(volumen[i]) if i < len(volumen) and volumen[i] is not None else None,
            )
        )
    ereignisse = []
    events = res.get("events") or {}
    for s in (events.get("splits") or {}).values():
        ereignisse.append(
            Ereignis(
                _datum(int(s["date"]), zone),
                "split",
                zaehler=Decimal(s["numerator"]),
                nenner=Decimal(s["denominator"]),
            )
        )
    for d in (events.get("dividends") or {}).values():
        ereignisse.append(
            Ereignis(_datum(int(d["date"]), zone), "dividende", wert=Decimal(d["amount"]))
        )
    name = meta.get("longName") or meta.get("shortName")
    ende = ((meta.get("currentTradingPeriod") or {}).get("regular") or {}).get("end")
    return Chart(
        symbol=str(meta.get("symbol") or ""),
        waehrung=meta.get("currency"),
        boerse=meta.get("fullExchangeName") or meta.get("exchangeName"),
        art=meta.get("instrumentType"),
        name=str(name) if name else None,
        zeitzone=zeitzone,
        kurse=sorted(kurse, key=lambda k: k.datum),
        ereignisse=sorted(ereignisse, key=lambda e: (e.datum, e.art)),
        handelsende=datetime.fromtimestamp(int(ende), UTC) if ende else None,
    )


@dataclass(frozen=True)
class Abruf:
    chart: Chart
    raw: rawstore.RawRef


class YahooClient:
    def __init__(
        self,
        cfg: dict[str, Any],
        agent: str,
        raw_dir: Path,
        *,
        fetcher: Callable[..., bytes] = fetch,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.cfg = cfg
        self.agent = agent
        self.raw_dir = raw_dir
        self.fetcher = fetcher
        self.sleep = sleep
        self.now = now
        self._gefragt = False

    def url(self, sym: str, zeitraum: str) -> str:
        query = urllib.parse.urlencode(
            {
                "range": zeitraum,
                "interval": "1d",
                "events": "div,split",
                "includeAdjustedClose": "true",
            }
        )
        basis = str(self.cfg["chart_url"]).format(symbol=urllib.parse.quote(sym))
        return f"{basis}?{query}"

    def chart(self, sym: str, zeitraum: str) -> Abruf:
        if self._gefragt:
            self.sleep(float(self.cfg["pause_s"]))
        self._gefragt = True
        url = self.url(sym, zeitraum)
        try:
            raw = self.fetcher(url, self.agent)
        except NotFound as exc:
            # Yahoo antwortet auf unbekannte Symbole mit 404 (geprüft am 14.10.2026)
            raise YahooError(f"Yahoo kennt {sym} nicht") from exc
        ref = rawstore.save(self.raw_dir, raw, url, self.now())
        return Abruf(parse_chart(raw), ref)
