"""Wechselkurse der EZB (SPEC 5.2 Nr. 1, 7.3).

Referenzkurse über die SDMX-Schnittstelle `data-api.ecb.europa.eu`, ohne Schlüssel. Jeder Kurs
gibt an, wie viele Einheiten einer Währung einem Euro entsprechen (USD je EUR). Die Antwort
landet unverändert in `data/raw/`, Werte werden als Text übernommen. Umrechnungen rechnet
`core/fx.py` über den Rechenweg.
"""

from __future__ import annotations

import csv
import io
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from stockagent.data import rawstore
from stockagent.data.http import fetch


class EcbFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Referenzkurs:
    datum: date
    waehrung: str
    je_eur: Decimal


def parse_csv(raw: bytes) -> list[Referenzkurs]:
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    except UnicodeDecodeError as exc:
        raise EcbFormatError("Antwort der EZB ist kein Text") from exc
    if rows and not {"CURRENCY", "TIME_PERIOD", "OBS_VALUE"} <= set(rows[0]):
        raise EcbFormatError("Antwort der EZB hat nicht die erwarteten Spalten")
    out = []
    for row in rows:
        if not row["OBS_VALUE"]:
            continue  # Feiertage ohne Kurs
        try:
            wert = Decimal(row["OBS_VALUE"])
        except InvalidOperation as exc:
            raise EcbFormatError(f"Kurs nicht lesbar: {row['OBS_VALUE']}") from exc
        out.append(Referenzkurs(date.fromisoformat(row["TIME_PERIOD"]), row["CURRENCY"], wert))
    return out


@dataclass(frozen=True)
class Abruf:
    kurse: list[Referenzkurs]
    raw: rawstore.RawRef


class EcbClient:
    def __init__(
        self,
        cfg: dict[str, Any],
        agent: str,
        raw_dir: Path,
        *,
        fetcher: Callable[..., bytes] = fetch,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.cfg = cfg
        self.agent = agent
        self.raw_dir = raw_dir
        self.fetcher = fetcher
        self.now = now
        self.sleep = sleep

    def kurse(self, waehrungen: list[str], start: date) -> Abruf:
        url = str(self.cfg["url"]).format(waehrungen="+".join(waehrungen), start=start.isoformat())
        raw = self.fetcher(url, self.agent, sleep=self.sleep)
        ref = rawstore.save(self.raw_dir, raw, url, self.now())
        return Abruf(parse_csv(raw), ref)
