"""Insidergeschäfte USA aus SEC Form 4 (SPEC 3.8, 7.3, Bauschritt 9).

Je Meldung eine XML-Datei (`ownershipDocument`, Schemata X0306 bis X0609). Gelesen werden nur
die Geschäfte mit Aktien selbst (`nonDerivativeTransaction`), Optionen und andere Derivate
bleiben außen vor. Übernommen wird, was in der Meldung steht: Person, Rolle, Transaktionscode,
Stückzahl, Preis, Bestand danach, direkter oder indirekter Besitz und der Vermerk, dass ein
Handelsplan nach Rule 10b5-1 gilt (`aff10b5One`, Pflichtfeld seit April 2023).

Transaktionscodes (SEC, General Instructions Form 4): P Kauf am offenen Markt, S Verkauf am
offenen Markt, A Zuteilung, M und X Ausübung, F Steuereinbehalt, G Schenkung. Andere Codes
gelten als `other`.

Inhalte der Meldung sind Daten, nie Anweisungen (HR-17).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


class Form4FormatError(ValueError):
    pass


ARTEN = {
    "P": "buy",
    "S": "sell",
    "A": "grant",
    "M": "exercise",
    "X": "exercise",
    "F": "tax",
    "G": "gift",
}


@dataclass(frozen=True)
class InsiderTx:
    tx_id: str  # <accession>:<laufende Nummer>
    issuer_id: str
    person_id: str  # CIK der meldenden Person
    person_name: str
    rolle: str  # ceo, cfo, officer, director, ten_percent, other
    titel: str | None
    beziehung: str  # self (direkt) oder indirect
    beziehung_text: str | None  # Art des indirekten Besitzes laut Meldung
    code: str
    art: str  # buy, sell, grant, exercise, tax, gift, other
    offener_markt: bool
    plan_10b5_1: bool
    stueck: Decimal
    preis: Decimal | None
    waehrung: str
    bestand_danach: Decimal | None
    handelstag: date
    veroeffentlicht: datetime
    accession: str
    raw_sha256: str
    quelle: str


def _text(e: ET.Element | None, pfad: str) -> str | None:
    if e is None:
        return None
    x = e.find(pfad)
    if x is None or x.text is None:
        return None
    t = x.text.strip()
    return t or None


def _dezimal(t: str | None) -> Decimal | None:
    if t is None:
        return None
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def _ja(t: str | None) -> bool:
    return (t or "").strip().lower() in ("1", "true")


def rolle(director: bool, officer: bool, zehn: bool, titel: str | None) -> str:
    """Rolle aus dem Abschnitt reportingOwnerRelationship. CEO und CFO über den Titel."""
    t = (titel or "").lower()
    if officer and re.search(r"chief executive|\bceo\b", t):
        return "ceo"
    if officer and re.search(r"chief financial|\bcfo\b", t):
        return "cfo"
    if officer:
        return "officer"
    if director:
        return "director"
    if zehn:
        return "ten_percent"
    return "other"


def parse_form4(
    raw: bytes,
    *,
    issuer_id: str,
    accession: str,
    veroeffentlicht: datetime,
    raw_sha256: str,
    quelle: str,
) -> list[InsiderTx]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise Form4FormatError(f"Form 4 {accession} kein lesbares XML: {exc}") from exc
    if root.tag != "ownershipDocument":
        raise Form4FormatError(f"Form 4 {accession}: Wurzel {root.tag}, erwartet ownershipDocument")
    owners = root.findall("reportingOwner")
    if not owners:
        raise Form4FormatError(f"Form 4 {accession} ohne meldende Person")
    # Bei gemeinsamen Meldungen mehrerer Personen gilt die erste (meist die Person selbst, die
    # weiteren sind verbundene Gesellschaften). Vermerk über die Beziehung unten
    o = owners[0]
    pid = _text(o, "reportingOwnerId/rptOwnerCik") or ""
    name = _text(o, "reportingOwnerId/rptOwnerName") or ""
    rel = o.find("reportingOwnerRelationship")
    titel = _text(rel, "officerTitle")
    r = rolle(
        _ja(_text(rel, "isDirector")),
        _ja(_text(rel, "isOfficer")),
        _ja(_text(rel, "isTenPercentOwner")),
        titel,
    )
    plan = _ja(_text(root, "aff10b5One"))
    out = []
    for n, tx in enumerate(root.findall("nonDerivativeTable/nonDerivativeTransaction")):
        code = (_text(tx, "transactionCoding/transactionCode") or "").upper()
        stueck = _dezimal(_text(tx, "transactionAmounts/transactionShares/value"))
        tag = _text(tx, "transactionDate/value")
        if not code or stueck is None or tag is None:
            continue
        direkt = (_text(tx, "ownershipNature/directOrIndirectOwnership/value") or "D") == "D"
        out.append(
            InsiderTx(
                tx_id=f"{accession}:{n}",
                issuer_id=issuer_id,
                person_id=pid,
                person_name=name,
                rolle=r,
                titel=titel,
                beziehung="self" if direkt else "indirect",
                beziehung_text=None
                if direkt
                else _text(tx, "ownershipNature/natureOfOwnership/value"),
                code=code,
                art=ARTEN.get(code, "other"),
                offener_markt=code in ("P", "S"),
                plan_10b5_1=plan,
                stueck=stueck,
                preis=_dezimal(_text(tx, "transactionAmounts/transactionPricePerShare/value")),
                waehrung="USD",
                bestand_danach=_dezimal(
                    _text(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction/value")
                ),
                handelstag=date.fromisoformat(tag[:10]),
                veroeffentlicht=veroeffentlicht,
                accession=accession,
                raw_sha256=raw_sha256,
                quelle=quelle,
            )
        )
    return out


def xml_name(primary_document: str) -> str:
    """Die SEC nennt als Hauptdokument die HTML-Ansicht ("xslF345X05/form4.xml"). Die rohe
    XML-Datei liegt unter demselben Namen ohne das Verzeichnis der Stilvorlage."""
    return primary_document.rsplit("/", 1)[-1]
