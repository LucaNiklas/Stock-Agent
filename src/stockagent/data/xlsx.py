"""Kleiner Leser für Excel-Dateien (.xlsx) ohne Zusatzbibliothek.

Damodaran veröffentlicht die monatliche Risikoprämie und die Branchenzuordnung nur als Excel.
Eine .xlsx-Datei ist ein ZIP-Archiv mit XML. Gelesen werden nur Zellwerte als Text, keine
Formeln, Formate oder Diagramme. Zahlen bleiben Text, umgerechnet wird in `core/`.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date, datetime

_ZEILE = re.compile(r"<row\b[^>]*>(.*?)</row>", re.S)
_ZELLE = re.compile(
    r'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>(.*?)</c>)',
    re.S,
)
_WERT = re.compile(r"<v>([^<]*)</v>")
_INLINE = re.compile(r"<t[^>]*>([^<]*)</t>")
_ENTITAETEN = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'"}


class XlsxFormatError(ValueError):
    pass


def _text(s: str) -> str:
    for k, v in _ENTITAETEN.items():
        s = s.replace(k, v)
    return s


def _spalte(buchstaben: str) -> int:
    """A -> 0, Z -> 25, AA -> 26. Stellenwert-Umrechnung eines Spaltennamens, kein Finanzwert."""
    nummer = 0
    for b in buchstaben:
        nummer = nummer * 26 + (ord(b) - 64)
    return nummer - 1


class Mappe:
    def __init__(self, raw: bytes) -> None:
        try:
            self._zip = zipfile.ZipFile(io.BytesIO(raw))
            self._wb = self._zip.read("xl/workbook.xml").decode("utf-8")
            rels = self._zip.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        except (zipfile.BadZipFile, KeyError) as exc:
            raise XlsxFormatError("keine Excel-Datei") from exc
        self.datum_1904 = "date1904" in self._wb
        ziele = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rels))
        ziele.update({k: v for v, k in re.findall(r'Target="([^"]+)"[^>]*Id="([^"]+)"', rels)})
        self.blaetter: dict[str, str] = {}
        for name, rid in re.findall(r'<sheet [^>]*name="([^"]+)"[^>]*r:id="([^"]+)"', self._wb):
            ziel = ziele[rid].lstrip("/")
            self.blaetter[_text(name)] = ziel if ziel.startswith("xl/") else f"xl/{ziel}"
        try:
            ss = self._zip.read("xl/sharedStrings.xml").decode("utf-8")
            self._strings = [
                _text("".join(_INLINE.findall(si)))
                for si in re.findall(r"<si>(.*?)</si>", ss, re.S)
            ]
        except KeyError:
            self._strings = []

    def zeilen(self, blatt: str) -> list[list[str | None]]:
        """Alle Zeilen eines Blatts, je Zeile die Zellen als Text (leer = None)."""
        if blatt not in self.blaetter:
            raise XlsxFormatError(f"Blatt {blatt!r} fehlt, vorhanden: {sorted(self.blaetter)}")
        xml = self._zip.read(self.blaetter[blatt]).decode("utf-8")
        out: list[list[str | None]] = []
        for body in _ZEILE.findall(xml):
            zellen: dict[int, str | None] = {}
            for ref, attr, inhalt in _ZELLE.findall(body):
                wert: str | None = None
                if 't="s"' in attr:
                    v = _WERT.search(inhalt or "")
                    wert = self._strings[int(v.group(1))] if v else None
                elif 't="inlineStr"' in attr:
                    wert = _text("".join(_INLINE.findall(inhalt or ""))) or None
                else:
                    v = _WERT.search(inhalt or "")
                    wert = _text(v.group(1)) if v and v.group(1) != "" else None
                zellen[_spalte(ref)] = wert
            breite = max(zellen, default=-1)
            out.append([zellen.get(i) for i in range(breite + 1)])
        return out

    def datum(self, seriennummer: str) -> date:
        """Excel-Datum aus der Seriennummer (Tage seit 1900 bzw. 1904, Mac-Dateien). Manche
        Zellen enthalten das Datum als Text, etwa „1-Sep-24“."""
        try:
            return excel_datum(int(float(seriennummer)), self.datum_1904)
        except ValueError:
            pass
        for fmt in ("%d-%b-%y", "%d-%b-%Y", "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(seriennummer.strip(), fmt).date()
            except ValueError:
                continue
        raise XlsxFormatError(f"Datum nicht lesbar: {seriennummer}")


def excel_datum(tage: int, datum_1904: bool) -> date:
    basis = date(1904, 1, 1) if datum_1904 else date(1899, 12, 30)
    return date.fromordinal(basis.toordinal() + tage)
