"""Zuordnung XBRL-Konzept zu interner Größe (`config/concept_map.yaml`, SPEC 7.2).

Je Periode gilt das erste Konzept der Vorrangliste, das für genau diese Periode einen Wert hat.
Reine Auswahl, keine Arithmetik.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from stockagent.data.store import StoredFact

Periode = tuple[date | None, date]


def load(config_dir: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((config_dir / "concept_map.yaml").read_text("utf-8"))
    return data


def resolve(facts: Iterable[StoredFact], concepts: list[str]) -> dict[Periode, StoredFact]:
    """Je Periode der Wert des ersten Konzepts der Liste, das dort einen Wert hat."""
    rang = {c: i for i, c in enumerate(concepts)}
    best: dict[Periode, StoredFact] = {}
    for f in facts:
        if f.concept not in rang:
            continue
        key = (f.period_start, f.period_end)
        alt = best.get(key)
        if alt is None or rang[f.concept] < rang[alt.concept]:
            best[key] = f
    return best
