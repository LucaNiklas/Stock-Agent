"""Kleine Beispieldateien im Format der echten Quellen (Deutsche Börse, GLEIF)."""

from __future__ import annotations

import io
import json
import zipfile

HEADER = [
    "Product Status",
    "Instrument Status",
    "Instrument",
    "ISIN",
    "Product ID",
    "Instrument ID",
    "WKN",
    "Mnemonic",
    "MIC Code",
    "Instrument Type",
    "Country Of Issue",
    "Currency",
    "Primary Market MIC Code",
]

# (Name, ISIN, WKN, Kürzel, Typ, Referenzmarkt)
STOCKS = [
    ("SIEMENS AG NA O.N.", "DE0007236101", "000723610", "SIE", "CS", "XFRA"),
    ("APPLE INC.", "US0378331005", "000865985", "APC", "CS", "XNAS"),
    ("SAP SE O.N.", "DE0007164600", "000716460", "SAP", "CS", "XETR"),
    ("ISHARES CORE MSCI WORLD", "IE00B4L5Y983", "000A0RPWH", "EUNL", "ETF", "XETR"),
    ("BUND 2030", "DE0001102507", "000110250", "BU30", "BOND", "XFRA"),
]


def instrument_csv(
    stocks: list[tuple[str, str, str, str, str, str]],
    market: str = "XFRA",
    as_of: str = "12.10.2026",
) -> bytes:
    lines = [f"Market:;{market}", f"Date Last Update:;{as_of}", ";".join(HEADER)]
    for name, isin, wkn, mnem, typ, mic in stocks:
        row = ["Active", "Active", name, isin, "1", "2", wkn, mnem, market, typ, "", "EUR", mic]
        lines.append(";".join(row))
    return ("\n".join(lines) + "\n").encode("utf-8")


def download_page(file_name: str) -> bytes:
    return (
        '<html><body><a href="/resource/blob/1/abc/data/QuoteParameters.csv">x</a>'
        f'<a href="/resource/blob/2/def/data/{file_name}">Download</a></body></html>'
    ).encode()


def gleif_zip(pairs: list[tuple[str, str]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "lei-isin-test.csv", "LEI,ISIN\n" + "".join(f"{lei},{isin}\n" for lei, isin in pairs)
        )
    return buf.getvalue()


def gleif_entities(entities: list[tuple[str, str, str, str]]) -> bytes:
    """Antwort der GLEIF-API mit (LEI, Name, rechtlicher Sitz, Hauptsitz)."""
    data = [
        {
            "id": lei,
            "attributes": {
                "entity": {
                    "legalName": {"name": name},
                    "legalAddress": {"country": legal},
                    "headquartersAddress": {"country": hq},
                    "status": "ACTIVE",
                }
            },
        }
        for lei, name, legal, hq in entities
    ]
    return json.dumps({"data": data}).encode()
