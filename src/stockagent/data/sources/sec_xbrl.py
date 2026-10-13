"""XBRL des Originalberichts lesen: zweiter, unabhängiger Weg zu den Company Facts (SPEC 3.2).

Die Company Facts sind eine Aufbereitung der SEC. Der zweite Weg liest die XBRL-Instanz der
Einreichung selbst (`*_htm.xml`, bei Inline-XBRL von der SEC aus dem Bericht extrahiert) und die
Berechnungsstruktur (`*_cal.xml`). Daraus entstehen:

- SPEC 3.2 Nr. 5: Abgleich der Kernwerte Company Facts gegen den Originalbericht.
- SPEC 3.2 Nr. 2: Summen der Unterpositionen gegen die Summenposition laut Berechnungsstruktur.

Nur Werte ohne Dimensionen (keine Segmente) werden genutzt. XML wird mit `defusedxml` gelesen,
weil heruntergeladene Dateien nicht vertrauenswürdig sind.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from defusedxml import ElementTree

_XBRLI = "{http://www.xbrl.org/2003/instance}"
_XLINK = "{http://www.w3.org/1999/xlink}"
_LINK = "{http://www.xbrl.org/2003/linkbase}"
_SUMMATION = (
    "http://www.xbrl.org/2003/arcrole/summation-item",
    "https://xbrl.org/2023/arcrole/summation-item",
)

# Namensraum -> Präfix der Taxonomie. Firmeneigene Konzepte bleiben außen vor.
_NAMESPACES = (
    (re.compile(r"^https?://fasb\.org/us-gaap/"), "us-gaap"),
    (re.compile(r"^https?://fasb\.org/srt/"), "srt"),
    (re.compile(r"^https?://xbrl\.sec\.gov/dei/"), "dei"),
    (re.compile(r"^https?://xbrl\.ifrs\.org/taxonomy/[^/]+/ifrs-full"), "ifrs-full"),
)


class XbrlFormatError(ValueError):
    pass


def choose_files(names: list[str]) -> tuple[str, str | None]:
    """Instanz und Datei mit der Berechnungsstruktur (`_cal.xml`, sonst das Schema) wählen."""
    inline = [n for n in names if n.endswith("_htm.xml")]
    if len(inline) == 1:
        instance = inline[0]
    else:
        plain = [
            n
            for n in names
            if n.endswith(".xml")
            and not re.search(r"_(cal|def|lab|pre)\.xml$", n)
            and n != "FilingSummary.xml"
        ]
        if len(plain) != 1:
            raise XbrlFormatError(f"Keine eindeutige XBRL-Instanz: {sorted(inline or plain)}")
        instance = plain[0]
    cal = [n for n in names if n.endswith("_cal.xml")]
    if len(cal) == 1:
        return instance, cal[0]
    # Manche Melder (etwa Microsoft) betten die Linkbases in das Schema ein
    xsd = [n for n in names if n.endswith(".xsd")]
    return instance, xsd[0] if len(xsd) == 1 else None


@dataclass(frozen=True)
class InstanceFact:
    concept: str
    value: Decimal
    unit_raw: str
    decimals: int | None
    period_start: date | None
    period_end: date


def _prefix(tag: str) -> str | None:
    if not tag.startswith("{"):
        return None
    uri, _, local = tag[1:].partition("}")
    for pattern, prefix in _NAMESPACES:
        if pattern.match(uri):
            return f"{prefix}:{local}"
    return None


def _measure(text: str) -> str:
    return text.strip().split(":")[-1]


def parse_instance(content: bytes) -> list[InstanceFact]:
    root = ElementTree.fromstring(content)
    if root.tag != f"{_XBRLI}xbrl":
        raise XbrlFormatError(f"Keine XBRL-Instanz: {root.tag}")
    contexts: dict[str, tuple[date | None, date]] = {}
    for ctx in root.iter(f"{_XBRLI}context"):
        if ctx.find(f"{_XBRLI}entity/{_XBRLI}segment") is not None:
            continue  # Werte mit Dimensionen
        if ctx.find(f"{_XBRLI}scenario") is not None:
            continue
        period = ctx.find(f"{_XBRLI}period")
        if period is None:
            continue
        instant = period.findtext(f"{_XBRLI}instant")
        if instant:
            contexts[ctx.get("id", "")] = (None, date.fromisoformat(instant.strip()))
        else:
            start = period.findtext(f"{_XBRLI}startDate")
            end = period.findtext(f"{_XBRLI}endDate")
            if start and end:
                contexts[ctx.get("id", "")] = (
                    date.fromisoformat(start.strip()),
                    date.fromisoformat(end.strip()),
                )
    units: dict[str, str] = {}
    for unit in root.iter(f"{_XBRLI}unit"):
        measures = [_measure(m.text or "") for m in unit.findall(f"{_XBRLI}measure")]
        num = [_measure(m.text or "") for m in unit.iter(f"{_XBRLI}unitNumerator")]
        den = [_measure(m.text or "") for m in unit.iter(f"{_XBRLI}unitDenominator")]
        if measures:
            units[unit.get("id", "")] = measures[0]
        elif num and den:
            n = unit.find(f"{_XBRLI}divide/{_XBRLI}unitNumerator/{_XBRLI}measure")
            d = unit.find(f"{_XBRLI}divide/{_XBRLI}unitDenominator/{_XBRLI}measure")
            if n is not None and d is not None:
                units[unit.get("id", "")] = f"{_measure(n.text or '')}/{_measure(d.text or '')}"
    seen: set[InstanceFact] = set()
    facts: list[InstanceFact] = []
    for el in root:
        concept = _prefix(el.tag)
        ctx_ref = el.get("contextRef")
        unit_ref = el.get("unitRef")
        if concept is None or ctx_ref is None or unit_ref is None:
            continue
        if ctx_ref not in contexts or unit_ref not in units:
            continue
        if el.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
            continue
        try:
            value = Decimal((el.text or "").strip())
        except InvalidOperation:
            continue
        dec = el.get("decimals")
        p_start, p_end = contexts[ctx_ref]
        fact = InstanceFact(
            concept=concept,
            value=value,
            unit_raw=units[unit_ref],
            decimals=None if dec is None or dec == "INF" else int(dec),
            period_start=p_start,
            period_end=p_end,
        )
        if fact not in seen:
            seen.add(fact)
            facts.append(fact)
    return facts


@dataclass(frozen=True)
class Summation:
    role: str
    parent: str
    children: tuple[tuple[str, Decimal], ...]  # (Konzept, Gewicht)


def _loc_concept(href: str) -> str | None:
    fragment = href.rpartition("#")[2]
    prefix, sep, local = fragment.partition("_")
    if not sep:
        return None
    return f"{prefix}:{local}" if prefix in ("us-gaap", "srt", "dei", "ifrs-full") else None


def parse_calculation(content: bytes) -> list[Summation]:
    root = ElementTree.fromstring(content)
    result = []
    for link in root.iter(f"{_LINK}calculationLink"):
        role = link.get(f"{_XLINK}role", "")
        labels: dict[str, str | None] = {
            loc.get(f"{_XLINK}label", ""): _loc_concept(loc.get(f"{_XLINK}href", ""))
            for loc in link.iter(f"{_LINK}loc")
        }
        children: dict[str, list[tuple[str, Decimal]]] = defaultdict(list)
        unknown_parent: set[str] = set()
        for arc in link.iter(f"{_LINK}calculationArc"):
            if arc.get(f"{_XLINK}arcrole") not in _SUMMATION:
                continue
            parent = labels.get(arc.get(f"{_XLINK}from", ""))
            child = labels.get(arc.get(f"{_XLINK}to", ""))
            if parent is None:
                continue
            if child is None:
                # Firmeneigenes Teilkonzept: Summe nicht vollständig prüfbar
                unknown_parent.add(parent)
                continue
            children[parent].append((child, Decimal(arc.get("weight", "1"))))
        for parent, kids in children.items():
            if parent not in unknown_parent:
                result.append(Summation(role, parent, tuple(kids)))
    return result
