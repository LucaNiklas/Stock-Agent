"""Platzhalter `{{metric_id@periode}}` auflösen und anzeigen (HR-01, SPEC 12.3).

Agenten schreiben Zahlen nur als Platzhalter, Python setzt die gespeicherten Werte ein. Perioden:

- `2025`: Jahreswert (`wert`) des Geschäftsjahres, das im Jahr 2025 endet
- `aktuell`, `ttm`: mit letztem Schlusskurs, letzte 12 Monate (am letzten Stichtag)
- Trendstatistiken am letzten Stichtag: `niveau`, `steigung`, `stdabw`, `cagr_5j`,
  `veraenderung_vj`, `perzentil_historie` und weitere aus `config/metrics.yaml`

Ein Platzhalter ohne gespeicherten Wert ist ein Fehler im Konsistenz-Gate (SPEC 12.6 Nr. 6).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from stockagent.core.anzeige import formatiere
from stockagent.data import store
from stockagent.gates.number import PLACEHOLDER

REF = re.compile(r"^([a-z][a-z0-9_]*)@([A-Za-z0-9_]+)$")
GELD = ("monetary", "per_share")


@dataclass(frozen=True)
class Wert:
    ref: str
    metric_id: str
    statistik: str
    period_end: date
    value: Any
    grund: str | None


class Werte:
    """Gespeicherte Kennzahlen einer Firma (letzter Lauf) für Platzhalter."""

    def __init__(
        self,
        rows: Iterable[store.MetricRow],
        stichtag: date | None,
        definitionen: dict[str, dict[str, Any]],
        waehrung: str | None,
    ) -> None:
        self.stichtag = stichtag
        self.defs = definitionen
        self.waehrung = waehrung
        self._je: dict[tuple[str, str, date], store.MetricRow] = {
            (r.metric_id, r.statistik, r.period_end): r for r in rows
        }

    @classmethod
    def laden(cls, conn: Any, issuer_id: str, metrics_cfg: dict[str, Any]) -> Werte:
        lauf = store.load_metric_run(conn, issuer_id)
        defs = {d["id"]: d for d in metrics_cfg["metrics"]}
        return cls(
            store.load_metrics(conn, issuer_id),
            lauf[2] if lauf else None,
            defs,
            store.report_currency(conn, issuer_id),
        )

    def hole(self, ref: str) -> Wert | None:
        m = REF.match(ref)
        if not m or m.group(1) not in self.defs or self.stichtag is None:
            return None
        metric_id, periode = m.groups()
        if periode.isdigit():
            treffer = [
                r
                for (mid, stat, _), r in self._je.items()
                if mid == metric_id and stat == "wert" and r.period_end.year == int(periode)
            ]
            row = treffer[0] if len(treffer) == 1 else None
        else:
            row = self._je.get((metric_id, periode, self.stichtag))
        if row is None:
            return None
        return Wert(ref, metric_id, row.statistik, row.period_end, row.value, row.grund)

    def anzeige(self, ref: str) -> str:
        w = self.hole(ref)
        if w is None:
            return f"[{ref} fehlt]"
        if w.value is None:
            return "unbekannt"
        d = self.defs[w.metric_id]
        anz, stellen = d["rundung"]["anzeige"], int(d["rundung"]["nachkommastellen"])
        geld = self.waehrung if d["einheit"] in GELD else None
        if w.statistik in ("cagr_5j", "veraenderung_vj", "perzentil_historie"):
            anz, stellen, geld = "percent", 1, None
        elif w.statistik in ("steigung", "stdabw") and anz == "percent":
            anz = "punkte"
        return formatiere(w.value, anz, stellen, geld)

    def ersetze(self, text: str) -> str:
        return PLACEHOLDER.sub(lambda m: self.anzeige(m.group(0)[2:-2]), text)

    def fehlend(self, refs: Iterable[str]) -> list[str]:
        return sorted({r for r in refs if self.hole(r) is None})


def refs_im_text(text: str) -> list[str]:
    return [m.group(0)[2:-2] for m in PLACEHOLDER.finditer(text)]
