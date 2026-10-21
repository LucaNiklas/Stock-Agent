"""J4 Endkontrolle (SPEC 11.2 Ebene 4, Bauschritt 10).

Deterministische Prüfung des fertigen Berichts, bevor er als fertig gilt. Kein Sprachmodell:
Alles, was J4 prüfen soll, lässt sich am Text und an der Entscheidung ablesen.

1. Aufbau: alle 14 Abschnitte in der Reihenfolge aus SPEC 12.3.
2. Platzhalter: keiner mehr offen (HR-01).
3. Urteil: Note und Kategorie im Bericht gleich `decision.json`.
4. These: der Text der geprüften These steht unverändert im Bericht (Zahlen wie berechnet).
5. Belege: jede geprüfte Aussage steht im Bericht und hat einen Beleg (Seite mit Zitat oder
   Kennzahl-Referenz).
6. Formulierung: keine Kaufaufforderung, kein Kursziel, keine Garantie (HR-15). Wörtliche Zitate
   aus Dokumenten zählen nicht, sie sind Daten (HR-17).
7. Gegenposition: jedes Risiko von A7 steht im Bericht, mit Erwiderung oder als offen markiert.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from stockagent.gates import wording

ABSCHNITTE = 14
_ZITAT = re.compile(r"„[^“]*“")


@dataclass(frozen=True)
class Befund:
    pruefung: str
    text: str


def _abschnitt(md: str, nr: int) -> str:
    m = re.search(rf"\n## {nr}\. [^\n]*\n(.*?)(?=\n## \d+\. |\Z)", md, re.S)
    return m.group(1) if m else ""


def _aussagen(knoten: Any) -> list[dict[str, Any]]:
    """Alle Aussagen im Berichtskontext: Einträge mit Text und Belegen, beliebig tief."""
    if isinstance(knoten, dict):
        if "belege" in knoten and "text" in knoten:
            return [knoten]
        return [a for v in knoten.values() for a in _aussagen(v)]
    if isinstance(knoten, list):
        return [a for v in knoten for a in _aussagen(v)]
    return []


def pruefen(md: str, entscheidung: dict[str, Any], kontext: dict[str, Any]) -> list[Befund]:
    out: list[Befund] = []

    # 1. Aufbau
    nummern = [int(n) for n in re.findall(r"\n## (\d+)\. ", md)]
    if nummern != list(range(1, ABSCHNITTE + 1)):
        out.append(Befund("aufbau", f"Abschnitte {nummern}, erwartet 1 bis {ABSCHNITTE}"))

    # 2. Platzhalter
    if "{{" in md or "}}" in md:
        out.append(Befund("platzhalter", "nicht ersetzter Platzhalter im Bericht"))

    # 3. Urteil gleich Entscheidung
    urteil = _abschnitt(md, 2)
    kategorie = str(entscheidung.get("kategorie") or "")
    note = str((entscheidung.get("note") or {}).get("note") or "")
    if kategorie and f"· {kategorie}**" not in urteil:
        out.append(Befund("urteil", f"Kategorie {kategorie} aus decision.json fehlt im Urteil"))
    if note and f"**Note {note} " not in urteil:
        out.append(Befund("urteil", f"Note {note} aus decision.json fehlt im Urteil"))

    # 4. These unverändert
    these = (kontext.get("these") or {}).get("text")
    if these and these not in _abschnitt(md, 3):
        out.append(Befund("these", "Text der geprüften These weicht im Bericht ab"))

    # 5. Belege: jede geprüfte Aussage steht mit mindestens einem Beleg im Bericht
    for c in _aussagen(kontext):
        if not c["belege"]:
            out.append(Befund("beleg", f"Aussage ohne Beleg: {c['text'][:80]}"))
        elif c["text"] not in md:
            out.append(Befund("beleg", f"Aussage fehlt im Bericht: {c['text'][:80]}"))

    # 6. Formulierung ohne Zitate aus Dokumenten
    ohne_zitate = _ZITAT.sub("„…“", md)
    for treffer in wording.offending(ohne_zitate):
        out.append(Befund("formulierung", f"unzulässige Formulierung '{treffer}' (HR-15)"))

    # 7. Gegenposition vollständig
    gegen = _abschnitt(md, 11)
    for i, r in enumerate((kontext.get("gegenposition") or {}).get("risiken", []), start=1):
        kopf = f"**Risiko {i}: {r['titel']}**"
        if kopf not in gegen:
            out.append(Befund("gegenposition", f"Risiko {i} ({r['titel']}) fehlt im Bericht"))
            continue
        teil = gegen.split(kopf, 1)[1].split("**Risiko ", 1)[0]
        if "Erwiderung" not in teil:
            out.append(Befund("gegenposition", f"Risiko {i} ohne Erwiderung oder Vermerk offen"))
    return out
