"""Normalisierung der Rechnungslegung (SPEC 4.3): Stand der Regeln ACC-01 bis ACC-14.

Die aktiven Regeln wirken dort, wo die Größe entsteht, nicht in einem eigenen Schritt: Leasing in
der Nettoverschuldung (`core/kennzahlen.py`, `data/inputs.py`), gezahlte Zinsen im freien
Cashflow, EBIT aus Komponenten, Pensionsdefizit und Minderheiten im Unternehmenswert
(`core/marktkennzahlen.py`). Regeln, die Angaben aus dem Anhang brauchen (Entwicklungskosten,
LIFO-Reserve, Wertaufholung, Neubewertung), sind offen, bis der PDF-Rückfall mit A2 gebaut ist,
und erscheinen im Bericht als nicht angewandt (HR-05, HR-16).

Diese Datei liest nur den Stand aus `config/accounting_adjustments.yaml` für Methodik-Ansicht und
Bericht. Sie rechnet nichts.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def regeln(cfg: Mapping[str, Any]) -> list[dict[str, str]]:
    """Je Regel ID, Thema, Status und Umsetzung oder Grund, in Reihenfolge der IDs."""
    out = []
    for rid, r in sorted((cfg.get("regeln") or {}).items()):
        out.append(
            {
                "id": str(rid),
                "thema": str(r.get("thema", "")),
                "status": str(r.get("status", "")),
                "text": " ".join(str(r.get("umsetzung") or r.get("grund") or "").split()),
            }
        )
    return out


def offen(cfg: Mapping[str, Any]) -> list[str]:
    """IDs der Regeln, die nicht (vollständig) angewandt werden."""
    return [r["id"] for r in regeln(cfg) if r["status"] != "aktiv"]
