"""Liste der handelbaren Aktien von Börse Frankfurt und Xetra (SPEC 7.1, ADR 0001).

Quelle sind die öffentlichen "All tradable instruments"-Dateien der Deutschen Börse. Sie sind
Semikolon-getrennt, Zeile 1 nennt den Markt, Zeile 2 das Datum, Zeile 3 die Spalten.
Übernommen werden nur Stammaktien (Instrument Type "CS").
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urljoin

REQUIRED = (
    "ISIN",
    "Instrument",
    "Instrument Type",
    "Instrument Status",
    "WKN",
    "Mnemonic",
    "Country Of Issue",
    "Currency",
    "Primary Market MIC Code",
)


class SourceFormatError(ValueError):
    """Die Datei hat nicht den erwarteten Aufbau. Lieber abbrechen als falsch einlesen."""


@dataclass(frozen=True)
class Instrument:
    isin: str
    name: str
    wkn: str
    mnemonic: str
    country_of_issue: str
    currency: str
    primary_mic: str
    status: str

    @property
    def isin_country(self) -> str:
        """Länderkürzel der ISIN (Land der ISIN-Vergabe, nicht zwingend der Firmensitz)."""
        return self.isin[:2]


@dataclass(frozen=True)
class InstrumentFile:
    market: str
    as_of: date
    instruments: list[Instrument]


def find_file_url(page_html: str, file_name: str, page_url: str) -> str:
    """Sucht den Link auf die Datei in der Downloadseite."""
    pattern = re.compile(r'href="([^"]*' + re.escape(file_name) + r')"')
    hits = sorted(set(pattern.findall(page_html)))
    if len(hits) != 1:
        raise SourceFormatError(f"{file_name}: {len(hits)} Links auf der Downloadseite gefunden")
    return urljoin(page_url, str(hits[0]))


def _wkn(raw: str) -> str:
    """Die Datei füllt die sechsstellige WKN mit drei Nullen auf neun Stellen auf."""
    return raw[3:] if len(raw) == 9 and raw.startswith("000") else raw


def parse(content: bytes) -> InstrumentFile:
    text = content.decode("utf-8-sig", errors="strict")
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    if len(rows) < 3 or rows[0][:1] != ["Market:"] or rows[1][:1] != ["Date Last Update:"]:
        raise SourceFormatError("Kopfzeilen 'Market:' und 'Date Last Update:' fehlen")
    market = rows[0][1]
    as_of = datetime.strptime(rows[1][1], "%d.%m.%Y").date()
    header = rows[2]
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        raise SourceFormatError(f"Spalten fehlen: {', '.join(missing)}")
    col = {name: header.index(name) for name in REQUIRED}
    instruments = []
    for line_no, row in enumerate(rows[3:], start=4):
        if not row:
            continue
        if len(row) != len(header):
            raise SourceFormatError(f"Zeile {line_no}: {len(row)} statt {len(header)} Spalten")
        if row[col["Instrument Type"]] != "CS":
            continue
        instruments.append(
            Instrument(
                isin=row[col["ISIN"]].strip(),
                name=row[col["Instrument"]].strip(),
                wkn=_wkn(row[col["WKN"]].strip()),
                mnemonic=row[col["Mnemonic"]].strip(),
                country_of_issue=row[col["Country Of Issue"]].strip(),
                currency=row[col["Currency"]].strip(),
                primary_mic=row[col["Primary Market MIC Code"]].strip(),
                status=row[col["Instrument Status"]].strip(),
            )
        )
    return InstrumentFile(market=market, as_of=as_of, instruments=instruments)
