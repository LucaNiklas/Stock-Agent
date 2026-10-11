"""Konsistenz-Gate (SPEC 12.6, Schritt 6).

Grundprüfung in Schritt 0: Jeder Platzhalter im Text muss in den berechneten Kennzahlen
existieren. Der Vergleich gegen `decision.json` folgt mit dem Renderer.
"""

from __future__ import annotations

from collections.abc import Mapping

from stockagent.gates import GateResult
from stockagent.gates.number import PLACEHOLDER


def check(text: str, metrics: Mapping[str, object]) -> GateResult:
    result = GateResult("consistency")
    for m in PLACEHOLDER.finditer(text):
        key = m.group(0)[2:-2]
        if key not in metrics:
            result.errors.append(f"Platzhalter ohne berechneten Wert: {key}")
    return result
