"""ISIN zu US-Ticker über OpenFIGI (ADR 0002).

OpenFIGI (Bloomberg) ordnet ISINs offiziell und kostenlos Wertpapierkennungen zu. Gebraucht wird
nur der Ticker an der US-Sammelbörse (`exchCode` = `US`). Die CIK liefert danach die Tickerliste
der SEC. Ohne API-Schlüssel gelten 25 Anfragen je Minute mit je 10 ISINs (live gemessen,
`config/sources.yaml`). Jede Antwort landet in `data/raw/`.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from stockagent.data import rawstore
from stockagent.data.http import fetch


class FigiFormatError(ValueError):
    pass


@dataclass(frozen=True)
class FigiResult:
    isin: str
    ticker: str | None  # eindeutiger Ticker an der US-Sammelbörse
    name: str | None
    note: str  # Begründung, wenn kein eindeutiger Ticker


def request_body(isins: list[str]) -> bytes:
    return json.dumps([{"idType": "ID_ISIN", "idValue": i} for i in isins]).encode()


def sec_ticker(ticker: str) -> str:
    """OpenFIGI schreibt Aktiengattungen mit Schrägstrich (BRK/B), die SEC mit Bindestrich."""
    return ticker.strip().upper().replace("/", "-").replace(" ", "-")


def parse_mapping(isins: list[str], raw: bytes) -> list[FigiResult]:
    answers = json.loads(raw)
    if not isinstance(answers, list) or len(answers) != len(isins):
        raise FigiFormatError("Antwort passt nicht zur Anfrage (Anzahl der Einträge)")
    results = []
    for isin, answer in zip(isins, answers, strict=True):
        if "data" not in answer:
            note = answer.get("warning") or answer.get("error") or "keine Daten"
            results.append(FigiResult(isin, None, None, f"OpenFIGI: {note}"))
            continue
        us = [d for d in answer["data"] if d.get("exchCode") == "US" and d.get("ticker")]
        tickers = sorted({sec_ticker(d["ticker"]) for d in us})
        name = us[0].get("name") if us else None
        if len(tickers) == 1:
            results.append(FigiResult(isin, tickers[0], name, ""))
        elif not tickers:
            results.append(FigiResult(isin, None, None, "OpenFIGI: kein Ticker an US-Börse"))
        else:
            results.append(
                FigiResult(isin, None, name, f"OpenFIGI: mehrere US-Ticker {', '.join(tickers)}")
            )
    return results


def batches(items: list[str], size: int) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class OpenFigiClient:
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
        self._gefragt = False  # Pause vor jeder Anfrage außer der allerersten, auch über Aufrufe

    def map(
        self, isins: list[str], progress: Callable[[int, int], None] | None = None
    ) -> list[FigiResult]:
        size = int(self.cfg["jobs_per_request"])
        pause = 60.0 / float(self.cfg["requests_per_minute"])
        results: list[FigiResult] = []
        for batch in batches(isins, size):
            if self._gefragt:
                self.sleep(pause)
            self._gefragt = True
            raw = self.fetcher(
                self.cfg["mapping_url"],
                self.agent,
                data=request_body(batch),
                headers={"Content-Type": "application/json"},
            )
            # Die Anfrage steht im Fragment, damit die Rohdatei nachvollziehbar bleibt
            url = f"{self.cfg['mapping_url']}#{','.join(batch)}"
            rawstore.save(self.raw_dir, raw, url, self.now())
            results.extend(parse_mapping(batch, raw))
            if progress:
                progress(len(results), len(isins))
        return results
