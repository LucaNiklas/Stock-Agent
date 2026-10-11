"""Zuordnung ISIN zu LEI aus der öffentlichen GLEIF-Datei (SPEC 7.1).

Die Datei ist ein ZIP mit einer CSV "LEI,ISIN" (mehrere Millionen Zeilen). Sie wird gestreamt,
behalten werden nur die gesuchten ISINs. Hat eine ISIN mehrere LEIs, bleibt sie ohne Zuordnung,
statt eine zu raten (HR-05).
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterable

from stockagent.data.sources.deutsche_boerse import SourceFormatError


def lei_by_isin(zip_content: bytes, isins: Iterable[str]) -> dict[str, str]:
    wanted = set(isins)
    found: dict[str, set[str]] = {}
    with zipfile.ZipFile(io.BytesIO(zip_content)) as archive:
        names = [n for n in archive.namelist() if n.endswith(".csv")]
        if len(names) != 1:
            raise SourceFormatError(f"GLEIF-ZIP enthält {len(names)} CSV-Dateien statt einer")
        with archive.open(names[0]) as handle:
            reader = csv.reader(io.TextIOWrapper(handle, encoding="utf-8"))
            if next(reader, None) != ["LEI", "ISIN"]:
                raise SourceFormatError("GLEIF-CSV hat nicht die Spalten LEI,ISIN")
            for lei, isin in reader:
                if isin in wanted:
                    found.setdefault(isin, set()).add(lei)
    return {isin: next(iter(leis)) for isin, leis in found.items() if len(leis) == 1}
