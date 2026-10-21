"""Risikofreie Zinsen (SPEC 3.6 Nr. 3, 7.3).

- EUR: Zinsstrukturkurve der Bundesbank (Svensson-Methode, börsennotierte Bundeswertpapiere),
  Restlaufzeit 10 Jahre, Tageswerte, Reihe BBSIS.D.I.ZST.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A.
- USD: Daily Treasury Par Yield Curve des US-Finanzministeriums, Spalte „10 Yr“, je Kalenderjahr
  eine Datei.

Beide ohne Schlüssel. Werte in Prozent, wie geliefert als Text (`Decimal`). Jede Antwort landet
unverändert in `data/raw/`.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from stockagent.data import rawstore
from stockagent.data.http import fetch


class ZinsFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Zins:
    datum: date
    serie: str  # rf_10y_EUR, rf_10y_USD
    prozent: Decimal


def parse_bundesbank(raw: bytes, serie: str = "rf_10y_EUR") -> list[Zins]:
    text = raw.decode("utf-8-sig")
    out = []
    kopf_gesehen = False
    for zeile in csv.reader(io.StringIO(text), delimiter=";"):
        if not zeile:
            continue
        if zeile[0].startswith("BBSIS") or (zeile[0] == "" and len(zeile) > 1):
            kopf_gesehen = True
            continue
        try:
            tag = date.fromisoformat(zeile[0])
        except ValueError:
            continue  # Kopfzeilen wie Einheit, Stand vom
        wert = zeile[1].strip() if len(zeile) > 1 else ""
        if wert in ("", "."):
            continue  # Wochenende, Feiertag
        try:
            out.append(Zins(tag, serie, Decimal(wert.replace(",", "."))))
        except InvalidOperation as exc:
            raise ZinsFormatError(f"Bundesbank: Zins nicht lesbar: {wert}") from exc
    if not kopf_gesehen:
        raise ZinsFormatError("Antwort der Bundesbank hat nicht die erwartete Form")
    return out


def parse_treasury(raw: bytes, serie: str = "rf_10y_USD", spalte: str = "10 Yr") -> list[Zins]:
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    if rows and ("Date" not in rows[0] or spalte not in rows[0]):
        raise ZinsFormatError(f"Treasury-Datei ohne Spalten Date und {spalte}")
    out = []
    for row in rows:
        wert = (row.get(spalte) or "").strip()
        if not wert or wert.upper() == "N/A":
            continue
        tag = datetime.strptime(row["Date"], "%m/%d/%Y").date()
        try:
            out.append(Zins(tag, serie, Decimal(wert)))
        except InvalidOperation as exc:
            raise ZinsFormatError(f"Treasury: Zins nicht lesbar: {wert}") from exc
    return sorted(out, key=lambda z: z.datum)


@dataclass(frozen=True)
class Abruf:
    zinsen: list[Zins]
    raw: rawstore.RawRef


class ZinsClient:
    def __init__(
        self,
        cfg: dict[str, Any],
        agent: str,
        raw_dir: Path,
        *,
        fetcher: Callable[..., bytes] = fetch,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.cfg = cfg
        self.agent = agent
        self.raw_dir = raw_dir
        self.fetcher = fetcher
        self.now = now

    def _hole(self, url: str) -> tuple[bytes, rawstore.RawRef]:
        raw = self.fetcher(url, self.agent)
        return raw, rawstore.save(self.raw_dir, raw, url, self.now())

    def bundesbank(self, start: date) -> Abruf:
        raw, ref = self._hole(str(self.cfg["bundesbank_url"]).format(start=start.isoformat()))
        return Abruf(parse_bundesbank(raw), ref)

    def treasury(self, jahr: int) -> Abruf:
        raw, ref = self._hole(str(self.cfg["treasury_url"]).format(jahr=jahr))
        return Abruf(parse_treasury(raw), ref)
