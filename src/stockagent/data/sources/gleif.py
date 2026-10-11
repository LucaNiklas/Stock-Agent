"""LEI-Daten der GLEIF (SPEC 7.1, ADR 0001).

1. Zuordnung ISIN zu LEI aus der öffentlichen ZIP-Datei ("LEI,ISIN", mehrere Millionen Zeilen).
   Sie wird gestreamt, behalten werden nur die gesuchten ISINs. Hat eine ISIN mehrere LEIs,
   bleibt sie ohne Zuordnung, statt eine zu raten (HR-05).
2. Stammdaten je LEI (rechtlicher Name, rechtlicher Sitz, Hauptsitz, Status) über die
   öffentliche GLEIF-API, bis zu 200 LEIs je Abfrage.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import quote

from stockagent.data.sources.deutsche_boerse import SourceFormatError


@dataclass(frozen=True)
class Entity:
    lei: str
    legal_name: str
    legal_country: str
    hq_country: str
    status: str
    jurisdiction: str | None = None
    other_names: tuple[str, ...] = ()

    @property
    def seat_country(self) -> str:
        """Rechtlicher Sitz: Land der Rechtsordnung (US-DE -> US), sonst Land der Adresse.

        Die eingetragene Adresse liegt bei Holdinggesellschaften oft woanders (Iveco N.V.: NL
        als Rechtsordnung, Adresse in Italien).
        """
        return (self.jurisdiction or self.legal_country)[:2]

    @property
    def all_names(self) -> tuple[str, ...]:
        """Rechtlicher Name, Namen in anderer Sprache, Umschriften und frühere Namen."""
        return (self.legal_name, *self.other_names)


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


def entity_urls(api_url: str, leis: Iterable[str], batch_size: int = 200) -> list[str]:
    """Abfrage-URLs für die GLEIF-API, je Abfrage höchstens batch_size LEIs."""
    ordered = sorted(set(leis))
    return [
        f"{api_url}?page%5Bsize%5D={batch_size}&filter%5Blei%5D="
        + quote(",".join(ordered[i : i + batch_size]), safe=",")
        for i in range(0, len(ordered), batch_size)
    ]


def parse_entities(content: bytes) -> dict[str, Entity]:
    try:
        records = json.loads(content)["data"]
        result = {}
        for rec in records:
            ent = rec["attributes"]["entity"]
            result[rec["id"]] = Entity(
                lei=rec["id"],
                legal_name=ent["legalName"]["name"],
                legal_country=ent["legalAddress"]["country"],
                hq_country=ent["headquartersAddress"]["country"],
                status=ent["status"],
                jurisdiction=ent.get("jurisdiction"),
                other_names=tuple(
                    o["name"]
                    for key in ("otherNames", "transliteratedOtherNames")
                    for o in ent.get(key) or []
                ),
            )
        return result
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SourceFormatError(f"GLEIF-API-Antwort unerwartet aufgebaut: {exc}") from exc
