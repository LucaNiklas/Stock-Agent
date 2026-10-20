"""Werkzeuge für Agenten (SPEC 16.1): nur lesen, nie schreiben.

- `rechenweg`: gespeicherter Rechenweg einer Zahl (A3, A7)
- `nachrechnen`: Werte unabhängig vom gespeicherten Lauf neu aus den Abschlusswerten rechnen,
  zum selben Datenstand (J1, SPEC 11.2). Liefert Wert und Rechenweg je Referenz.
"""

from __future__ import annotations

import json
from datetime import UTC
from typing import Any

from stockagent import metrics_update
from stockagent.data import store
from stockagent.paths import Paths
from stockagent.platzhalter import REF


def _kurz(trace: dict[str, Any]) -> list[dict[str, Any]]:
    schritte = [
        {"schritt": s["name"], "formel": s["formel"], "ergebnis": s["ergebnis"]}
        for s in trace.get("schritte", [])
    ]
    return [
        *schritte,
        *[
            {"pruefpunkt": p["cp_id"], "text": p["text"], "bestanden": p["bestanden"]}
            for p in trace.get("pruefungen", [])
        ],
    ]


def _issuer(conn: Any, isin: str) -> str:
    issuer = metrics_update.issuer_for_isin(conn, isin.upper())
    if issuer is None:
        raise ValueError(f"{isin}: kein SEC-Melder")
    return issuer


def rechenweg(paths: Paths, isin: str, ref: str) -> dict[str, Any]:
    m = REF.match(ref)
    if not m:
        return {"ref": ref, "fehler": "Form metric_id@periode erwartet"}
    conn = store.connect_read(paths.db)
    try:
        issuer = _issuer(conn, isin)
        lauf = store.load_metric_run(conn, issuer)
        mid, periode = m.groups()
        for r in store.load_metrics(conn, issuer, metric_id=mid):
            treffer = (
                r.statistik == "wert" and str(r.period_end.year) == periode
                if periode.isdigit()
                else r.statistik == periode and lauf is not None and r.period_end == lauf[2]
            )
            if treffer and r.calc_trace_json:
                trace = _kurz(json.loads(r.calc_trace_json))
                return {"ref": ref, "wert": str(r.value), "rechenweg": trace}
            if treffer:
                return {"ref": ref, "wert": str(r.value), "rechenweg": "nur Wert gespeichert"}
    finally:
        conn.close()
    return {"ref": ref, "fehler": "kein gespeicherter Wert"}


def nachrechnen(paths: Paths, isin: str, refs: list[str]) -> list[dict[str, Any]]:
    """Alle Kennzahlen einmal neu rechnen (zum Datenstand des gespeicherten Laufs) und die
    gefragten Referenzen heraussuchen."""
    cfg = metrics_update.Konfiguration.laden(paths.config)
    conn = store.connect_read(paths.db)
    try:
        issuer = _issuer(conn, isin)
        lauf = store.load_metric_run(conn, issuer)
        if lauf is None:
            return [{"ref": r, "status": "not_computable", "grund": "kein Lauf"} for r in refs]
        as_of = lauf[1].replace(tzinfo=UTC)
        rechnung = metrics_update.berechne(conn, issuer, as_of, cfg)
    finally:
        conn.close()
    out: list[dict[str, Any]] = []
    for ref in refs:
        m = REF.match(ref)
        if not m:
            out.append({"ref": ref, "status": "not_computable", "grund": "Form metric_id@periode"})
            continue
        mid, periode = m.groups()
        treffer = [
            w
            for w in rechnung.werte
            if w.metric_id == mid
            and (
                (w.statistik == "wert" and str(w.period_end.year) == periode)
                if periode.isdigit()
                else (w.statistik == periode and w.period_end == rechnung.stichtag)
            )
        ]
        if not treffer or treffer[0].ergebnis.wert is None:
            grund = treffer[0].ergebnis.grund if treffer else "Referenz nicht berechenbar"
            out.append({"ref": ref, "status": "not_computable", "grund": grund})
            continue
        e = treffer[0].ergebnis
        out.append(
            {
                "ref": ref,
                "status": "berechnet",
                "wert": str(e.wert),
                "rechenweg": _kurz(e.rechenweg) if e.rechenweg else [],
            }
        )
    return out
