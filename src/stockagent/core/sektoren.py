"""Branche, Scorecard, Region und Größenklasse (SPEC 3.1, 3.11, 6.2, 7.8). Reine Zuordnung."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Branche:
    haupt: str
    haupt_name: str
    unter: str
    unter_name: str


def branche(sic: int | None, cfg: Mapping[str, Any]) -> Branche | None:
    """Unterbranche zum SIC-Code. Passen mehrere Bereiche, zählt der engste."""
    if sic is None:
        return None
    treffer: list[tuple[int, Branche]] = []
    for hid, h in cfg["hauptbranchen"].items():
        for uid, u in h["unter"].items():
            for von, bis in u["sic"]:
                if int(von) <= sic <= int(bis):
                    breite = int(bis) - int(von)
                    treffer.append((breite, Branche(hid, h["name"], uid, u["name"])))
    return min(treffer, key=lambda x: x[0])[1] if treffer else None


@dataclass(frozen=True)
class Scorecard:
    id: str
    ab_schritt: int


def scorecard(
    sic: int | None,
    wachstum_ohne_gewinn: bool,
    cfg: Mapping[str, Any],
    holding: bool = False,
) -> Scorecard:
    """Erste passende Regel aus `config/scorecards.yaml` (SPEC 3.11). Die Kennzahlregeln
    (Holding, Wachstum ohne Gewinn) wertet `bewertung.py` aus und reicht das Ergebnis herein."""
    for regel in cfg["zuordnung"]:
        if "sic" in regel:
            if sic is not None and any(int(a) <= sic <= int(b) for a, b in regel["sic"]):
                return Scorecard(regel["scorecard"], int(regel["ab_schritt"]))
        elif regel.get("regel") == "wachstum_ohne_gewinn":
            if wachstum_ohne_gewinn:
                return Scorecard(regel["scorecard"], int(regel["ab_schritt"]))
        elif regel.get("regel") == "holding":
            if holding:
                return Scorecard(regel["scorecard"], int(regel["ab_schritt"]))
        else:
            return Scorecard(regel["scorecard"], int(regel["ab_schritt"]))
    raise ValueError("config/scorecards.yaml ohne Standardregel")


def region(land: str | None, regionen: Mapping[str, list[str]]) -> str | None:
    for name, laender in regionen.items():
        if land in laender:
            return name
    return None
