"""Zahlen-Gate (HR-01).

Prüft nur Freitextfelder (Marker `FREE_TEXT`). Erlaubt sind Platzhalter `{{metric_id@periode}}`,
Kennzahl-IDs, Seitenangaben und Jahreszahlen. Jede andere Ziffer ist ein Verstoß. Zitate stehen
im Feld `quote` und werden vom Zitat-Gate geprüft, nicht hier.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from stockagent.gates import GateResult
from stockagent.schemas.base import FREE_TEXT

PLACEHOLDER = re.compile(r"\{\{[a-z][a-z0-9_]*@[A-Za-z0-9_.\-]+\}\}")
METRIC_ID = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
PAGE_REF = re.compile(
    r"\b(?:S\.|Seite|Seiten|p\.|pp\.|page|pages)\s*\d{1,4}(?:\s*(?:-|–|bis|to)\s*\d{1,4})?",
    re.IGNORECASE,
)
YEAR = re.compile(r"(?<![\d.,])(?:19|20)\d{2}(?![\d.,%])")
DIGIT = re.compile(r"\d")
# Ausgeschriebene Zahlen vor einer Einheit („drei Prozent“, „zwanzig Milliarden“) und
# Vervielfachungen („verdoppelt“, „halbiert“) sind Finanzwerte in Worten (HR-01). Zählwörter ohne
# Einheit („zwei Segmente“) bleiben erlaubt.
ZAHLWORT = (
    r"(?:zwei|drei|vier|fünf|fuenf|sechs|sieben|acht|neun|zehn|elf|zwölf|zwoelf|"
    r"\w*zehn|\w*zig|\w*ßig|\w*hundert\w*|\w*tausend\w*|halbe[nrs]?|eineinhalb|anderthalb|"
    r"one|two|three|four|five|six|seven|eight|nine|ten|twenty|thirty|forty|fifty|hundred|thousand)"
)
EINHEIT = (
    r"(?:prozent\w*|prozentpunkt\w*|basispunkt\w*|mio\.?|millionen?|mrd\.?|milliarden?|"
    r"billionen?|euro|dollar|usd|eur|cent|mal|fache?n?|percent|million|billion|times)"
)
ZAHL_IN_WORTEN = re.compile(
    rf"\b{ZAHLWORT}\s*-?\s*{EINHEIT}\b"
    r"|\b(?:ver(?:doppel|dreifach|vierfach|zehnfach)\w*|halbier\w*|gedrittelt|"
    r"doubled|tripled|halved)\b",
    re.IGNORECASE,
)


def offending(text: str) -> list[str]:
    """Liefert die Textstellen mit unerlaubten Ziffern."""
    cleaned = text
    for pattern in (PLACEHOLDER, PAGE_REF, METRIC_ID, YEAR):
        cleaned = pattern.sub(lambda m: " " * len(m.group(0)), cleaned)
    hits = []
    for m in DIGIT.finditer(cleaned):
        start = max(0, m.start() - 15)
        hits.append(text[start : m.end() + 15].strip())
    hits.extend(m.group(0) for m in ZAHL_IN_WORTEN.finditer(cleaned))
    return hits


def free_text_fields(obj: BaseModel, path: str = "") -> list[tuple[str, str]]:
    """Alle Freitextfelder eines Modells mit Pfad, rekursiv."""
    found: list[tuple[str, str]] = []
    for name, info in type(obj).model_fields.items():
        value = getattr(obj, name)
        where = f"{path}{name}"
        if FREE_TEXT in info.metadata and isinstance(value, str):
            found.append((where, value))
        elif isinstance(value, BaseModel):
            found.extend(free_text_fields(value, f"{where}."))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, BaseModel):
                    found.extend(free_text_fields(item, f"{where}[{i}]."))
    return found


def check(obj: BaseModel) -> GateResult:
    result = GateResult("number")
    for where, text in free_text_fields(obj):
        for snippet in offending(text):
            result.errors.append(f"{where}: Zahl ohne Platzhalter in '{snippet}'")
    return result
