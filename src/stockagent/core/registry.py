"""Formelregister (SPEC 12.2, HR-06).

Jede Kennzahl aus `config/metrics.yaml` hat genau eine hier registrierte Funktion. Eine
Kennzahlfunktion bekommt Rechenweg, Jahresreihen und Stichtag und gibt den Wert zurück. `berechne`
legt den Rechenweg mit den Pflicht-Prüfpunkten aus dem Register an und macht aus einem
verletzten Prüfpunkt oder einer fehlenden Eingabe ein `unknown` mit Grund.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from stockagent.core.calc import Ergebnis, Rechenweg, rechne
from stockagent.core.reihen import Reihen

MetricFn = Callable[[Rechenweg, Reihen, date], Decimal]

_REGISTRY: dict[str, MetricFn] = {}


def metric(metric_id: str) -> Callable[[MetricFn], MetricFn]:
    def register(fn: MetricFn) -> MetricFn:
        if metric_id in _REGISTRY:
            raise ValueError(f"Kennzahl doppelt registriert: {metric_id}")
        _REGISTRY[metric_id] = fn
        return fn

    return register


def get(metric_id: str) -> MetricFn:
    return _REGISTRY[metric_id]


def ids() -> set[str]:
    return set(_REGISTRY)


def berechne(definition: Mapping[str, Any], reihen: Reihen, stichtag: date) -> Ergebnis:
    """Eine Kennzahl für ein Geschäftsjahr über den Rechenweg (HR-19)."""
    metric_id = str(definition["id"])
    r = Rechenweg(
        metric_id,
        str(definition["version"]),
        reihen.subjekt,
        stichtag.isoformat(),
        pflicht=tuple(definition["pruefpunkte"]),
    )
    return rechne(r, lambda r: get(metric_id)(r, reihen, stichtag))


# Registrierung der Kennzahlen und Scores beim Import (Dekorator oben muss zuerst stehen)
from stockagent.core import (  # noqa: E402
    kapitalkosten,
    kennzahlen,
    marktkennzahlen,
    scores,
    szenarien,
)

__all__ = [
    "berechne",
    "get",
    "ids",
    "kapitalkosten",
    "kennzahlen",
    "marktkennzahlen",
    "metric",
    "scores",
    "szenarien",
]
