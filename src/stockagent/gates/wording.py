"""Formulierungs-Gate (HR-15): keine Kursziele, Renditeversprechen oder Handlungsaufforderungen."""

from __future__ import annotations

import re

from pydantic import BaseModel

from stockagent.gates import GateResult
from stockagent.gates.number import free_text_fields

FORBIDDEN = [
    r"\b(jetzt|sofort)\s+(kaufen|verkaufen|einsteigen|zugreifen)\b",
    r"\b(kaufen|verkaufen)\s+sie\b",
    r"\bsie\s+sollten\s+(\w+\s+)?(kaufen|verkaufen)\b",
    r"\b(kauf|verkauf)s?empfehlung\w*\b",
    r"\bkursziel\w*\b",
    r"\bgarantiert\w*\b",
    r"\b(sichere|sicherer|garantierte)\s+rendite\b",
    r"\bstrong\s+(buy|sell)\b",
    r"\bprice\s+target\b",
    r"\b(buy|sell)\s+rating\b",
    r"\bkaufchance\w*\b",
    r"\b(einstieg|kauf)s?(chance|gelegenheit|signal|zeitpunkt)\w*\b",
    r"\bverkaufssignal\w*\b",
    r"\b(zugreifen|zuschlagen)\b",
    r"\b(über|ueber|unter)gewichten\b",
    r"\b(akkumulieren|nachkaufen|aufstocken|glattstellen)\b",
    r"\b(outperform|underperform|overweight|underweight)\w*\b",
    r"\blohnt\s+sich\s+(ein|der|jetzt)?\s*(kauf|einstieg|verkauf)\b",
    r"\b(man|anleger|investoren)\s+sollten?\s+(\w+\s+){0,3}(kaufen|verkaufen|einsteigen)\b",
    r"\b(kurs|aufwärts|aufwaerts)potenzial\w*\b",
    r"\bupside\b",
    r"\bkursverdopp\w*\b",
]
_PATTERN = re.compile("|".join(FORBIDDEN), re.IGNORECASE)


def offending(text: str) -> list[str]:
    return [m.group(0) for m in _PATTERN.finditer(text)]


def check(obj: BaseModel) -> GateResult:
    result = GateResult("wording")
    for where, text in free_text_fields(obj):
        for hit in offending(text):
            result.errors.append(f"{where}: unzulässige Formulierung '{hit}'")
    return result
