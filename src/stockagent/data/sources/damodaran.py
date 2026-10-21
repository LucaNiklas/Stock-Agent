"""Datensätze von Aswath Damodaran, NYU Stern (SPEC 3.6 Nr. 3, 7.3).

- Branchenbetas USA (`Betas.html`): unverschuldetes Beta, bereinigt um Kasse, je Branche.
- Rating nach Zinsdeckung und Zinsaufschlag (`ratings.html`): synthetisches Rating für die
  Fremdkapitalkosten. Die Seite enthält die Tabelle für große Nicht-Finanzfirmen und für
  Finanzfirmen.
- Implizite Aktienrisikoprämie je Monat (`ERPbymonth.xlsx`, Spalte „ERP (T12m)“).
- Branchenzuordnung aller Firmen weltweit (`indname.xlsx`, Blatt „By industry“): Firma,
  Börse:Kürzel, Branche, SIC-Code, Land.

Werte bleiben Text wie geliefert, Prozentangaben ohne Umrechnung. Gespeichert wird je Abruf ein
datierter Stand (SPEC 7.3: „als datierter Snapshot speichern“).
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from stockagent.data import rawstore
from stockagent.data.http import fetch
from stockagent.data.xlsx import Mappe, XlsxFormatError


class DamodaranFormatError(ValueError):
    pass


def _zellen(zeile: str) -> list[str]:
    roh = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", zeile, re.S | re.I)
    return [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", c))).strip() for c in roh]


def tabelle(raw: bytes) -> list[list[str]]:
    text = raw.decode("latin-1")
    return [_zellen(z) for z in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S | re.I)]


def _dezimal(text: str) -> Decimal | None:
    """Zahl wie geliefert. Prozentzeichen bleibt als Angabe in Prozent erhalten (kein Teilen)."""
    t = text.replace(",", "").replace("%", "").strip()
    if t in ("", "NA", "N/A", "#DIV/0!"):
        return None
    try:
        return Decimal(t)
    except InvalidOperation as exc:
        raise DamodaranFormatError(f"Zahl nicht lesbar: {text}") from exc


def stand(raw: bytes) -> str | None:
    """„Data used is as of January 2026“ oder „Date : January 2026“ aus dem Seitenkopf."""
    text = re.sub(r"<[^>]+>", " ", raw.decode("latin-1"))
    m = re.search(r"(?:as of|Date\s*:)\s*([A-Z][a-z]+ \d{4})", text)
    return m.group(1) if m else None


@dataclass(frozen=True)
class Branchenbeta:
    branche: str
    firmen: int
    beta: Decimal | None
    de_prozent: Decimal | None
    steuer_prozent: Decimal | None
    beta_unverschuldet: Decimal | None
    kasse_prozent: Decimal | None
    beta_unverschuldet_kasse: Decimal | None


def parse_betas(raw: bytes) -> list[Branchenbeta]:
    zeilen = tabelle(raw)
    kopf = next((i for i, z in enumerate(zeilen) if z and z[0] == "Industry Name"), None)
    if kopf is None or "Unlevered beta corrected for cash" not in zeilen[kopf]:
        raise DamodaranFormatError("Betas.html ohne erwartete Kopfzeile")
    sp = {name: i for i, name in enumerate(zeilen[kopf])}
    out = []
    for z in zeilen[kopf + 1 :]:
        if len(z) < len(sp) or not z[0]:
            continue
        out.append(
            Branchenbeta(
                branche=z[0],
                firmen=int(z[sp["Number of firms"]].replace(",", "")),
                beta=_dezimal(z[sp["Beta"]]),
                de_prozent=_dezimal(z[sp["D/E Ratio"]]),
                steuer_prozent=_dezimal(z[sp["Effective Tax rate"]]),
                beta_unverschuldet=_dezimal(z[sp["Unlevered beta"]]),
                kasse_prozent=_dezimal(z[sp["Cash/Firm value"]]),
                beta_unverschuldet_kasse=_dezimal(z[sp["Unlevered beta corrected for cash"]]),
            )
        )
    if not out:
        raise DamodaranFormatError("Betas.html ohne Branchen")
    return out


@dataclass(frozen=True)
class Ratingstufe:
    art: str  # nichtfinanz (große Nicht-Finanzfirmen) oder finanz
    deckung_ab: Decimal  # Zinsdeckung größer als dieser Wert ...
    deckung_bis: Decimal  # ... und höchstens dieser
    rating: str
    aufschlag_prozent: Decimal


def parse_ratings(raw: bytes) -> list[Ratingstufe]:
    out = []
    for z in tabelle(raw):
        if len(z) < 4 or not re.fullmatch(r"-?\d+(\.\d+)?", z[0].strip()):
            continue
        teile = [("nichtfinanz", z[0:4])]
        if len(z) >= 9 and re.fullmatch(r"-?\d+(\.\d+)?", z[5].strip()):
            teile.append(("finanz", z[5:9]))
        for art, (ab, bis, rating, aufschlag) in teile:
            a, b, s = _dezimal(ab), _dezimal(bis), _dezimal(aufschlag)
            if a is None or b is None or s is None:
                raise DamodaranFormatError(f"Ratingzeile unvollständig: {z}")
            out.append(Ratingstufe(art, a, b, rating, s))
    if not any(r.art == "nichtfinanz" for r in out):
        raise DamodaranFormatError("ratings.html ohne Tabelle für Nicht-Finanzfirmen")
    return out


def _anteil(text: str) -> Decimal:
    """Zelle als Anteil: „0.039“ bleibt, „3.90%“ (als Text gespeicherte Zelle) wird 0.0390.
    Verschiebung des Kommas beim Lesen des Formats, keine Rechnung."""
    t = text.strip()
    try:
        return Decimal(t[:-1]).scaleb(-2) if t.endswith("%") else Decimal(t)
    except InvalidOperation as exc:
        raise DamodaranFormatError(f"Zahl nicht lesbar: {text}") from exc


@dataclass(frozen=True)
class Risikopraemie:
    monat: date  # Monatsanfang
    erp: Decimal  # Anteil, etwa 0.0437 für 4,37 %
    tbond: Decimal | None


def parse_erp(raw: bytes, spalte: str = "ERP (T12m)") -> list[Risikopraemie]:
    try:
        mappe = Mappe(raw)
        zeilen = mappe.zeilen("Historical ERP")
    except XlsxFormatError as exc:
        raise DamodaranFormatError(f"ERPbymonth.xlsx: {exc}") from exc
    kopf = zeilen[0] if zeilen else []
    if "Start of month" not in kopf or spalte not in kopf:
        raise DamodaranFormatError(f"ERPbymonth.xlsx ohne Spalten Start of month und {spalte}")
    i_tag, i_erp = kopf.index("Start of month"), kopf.index(spalte)
    i_bond = kopf.index("T.Bond Rate") if "T.Bond Rate" in kopf else None
    out = []
    for z in zeilen[1:]:
        if len(z) <= i_erp or not z[i_tag] or not z[i_erp]:
            continue
        bond = z[i_bond] if i_bond is not None and len(z) > i_bond else None
        out.append(
            Risikopraemie(
                mappe.datum(str(z[i_tag])),
                _anteil(str(z[i_erp])),
                _anteil(bond) if bond else None,
            )
        )
    return sorted(out, key=lambda r: r.monat)


@dataclass(frozen=True)
class Firmenbranche:
    firma: str
    boerse_kuerzel: str  # etwa NasdaqGS:AAPL
    branche: str
    sic: str | None
    land: str | None


def parse_indname(raw: bytes) -> list[Firmenbranche]:
    try:
        zeilen = Mappe(raw).zeilen("By industry")
    except XlsxFormatError as exc:
        raise DamodaranFormatError(f"indname.xlsx: {exc}") from exc
    kopf = zeilen[0] if zeilen else []
    noetig = ["Company Name", "Exchange:Ticker", "Industry Group", "SIC Code", "Country"]
    if any(k not in kopf for k in noetig):
        raise DamodaranFormatError("indname.xlsx ohne erwartete Spalten")
    i = {k: kopf.index(k) for k in noetig}

    def feld(z: list[str | None], k: str) -> str | None:
        return z[i[k]] if len(z) > i[k] else None

    out = []
    for z in zeilen[1:]:
        branche, kuerzel = feld(z, "Industry Group"), feld(z, "Exchange:Ticker")
        if not branche or not kuerzel:
            continue
        sic = feld(z, "SIC Code")
        out.append(
            Firmenbranche(
                " ".join(str(feld(z, "Company Name") or "").split()),
                kuerzel,
                branche,
                sic.split(".")[0] if sic else None,
                feld(z, "Country"),
            )
        )
    return out


@dataclass(frozen=True)
class Abruf:
    raw: bytes
    ref: rawstore.RawRef


class DamodaranClient:
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

    def hole(self, schluessel: str) -> Abruf:
        url = str(self.cfg[schluessel])
        raw = self.fetcher(url, self.agent)
        return Abruf(raw, rawstore.save(self.raw_dir, raw, url, self.now()))
