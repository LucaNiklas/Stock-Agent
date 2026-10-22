"""Ansichten Änderungen, Historie und Methodik (SPEC 13.3, ADR 0014). Nur Lesen, kein Modell.

- Änderungen: neue Noten, Noten- und Kategoriewechsel, neue Berichte, Restatements,
  Insiderkäufe und Indexauf- und -abstiege seit dem vorletzten Tagesstand der Noten
  (`grade_snapshots`).
- Historie: Notenverlauf je Titel und Stand der Notenkontrolle (SPEC 14).
- Methodik: Versionen, Gewichte und Schwellen aus `config/`, Änderungsprotokoll.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

import yaml

from stockagent.data import store
from stockagent.paths import Paths

CHANGELOG = "docs/METHODOLOGY_CHANGELOG.md"


def methodik_version(paths: Paths) -> str:
    """Letzte Version im Änderungsprotokoll, dazu die Version der Kennzahlen."""
    datei = paths.root / CHANGELOG
    version = "unbekannt"
    if datei.exists():
        gefunden = re.findall(r"^## (\d+\.\d+)", datei.read_text("utf-8"), flags=re.M)
        version = gefunden[-1] if gefunden else version
    m = yaml.safe_load((paths.config / "metrics.yaml").read_text("utf-8"))
    return f"{version} (Kennzahlen {m.get('methodology_version', '?')})"


# ------------------------------------------------------------------ Änderungen


def _tag(x: Any) -> str:
    return x.isoformat() if isinstance(x, (date, datetime)) else str(x)


def aenderungen(paths: Paths, seit: date | None = None) -> dict[str, Any]:
    """Was sich seit dem letzten Lauf geändert hat. Ohne `seit`: seit dem vorletzten Tag mit
    eingefrorenen Noten. Gibt es nur einen Tag, gilt alles als neu (`seit` ist dann None)."""
    conn = store.connect_read(paths.db)
    try:
        tage = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT snapshot_date FROM grade_snapshots ORDER BY 1 DESC"
            ).fetchall()
        ]
        erster_stand = seit is None and len(tage) < 2
        if seit is None:
            seit = tage[1] if len(tage) > 1 else date(1900, 1, 1)
        namen = dict(conn.execute("SELECT isin, name FROM listings").fetchall())
        # Letzter Stand je Titel nach `seit` gegen den letzten Stand bis `seit`
        noten = conn.execute(
            "WITH neu AS (SELECT isin, arg_max(grade, snapshot_date) AS note, "
            "arg_max(kategorie, snapshot_date) AS kat, max(snapshot_date) AS tag "
            "FROM grade_snapshots WHERE snapshot_date > ? GROUP BY isin), "
            "alt AS (SELECT isin, arg_max(grade, snapshot_date) AS note, "
            "arg_max(kategorie, snapshot_date) AS kat FROM grade_snapshots "
            "WHERE snapshot_date <= ? GROUP BY isin) "
            "SELECT neu.isin, alt.note, neu.note, alt.kat, neu.kat, neu.tag FROM neu "
            "LEFT JOIN alt ON alt.isin = neu.isin "
            "WHERE alt.isin IS NULL OR alt.note <> neu.note OR alt.kat IS DISTINCT FROM neu.kat "
            "ORDER BY neu.tag DESC, neu.isin",
            [seit, seit],
        ).fetchall()
        isin_von = dict(
            conn.execute(
                "SELECT 'sec:' || cik, isin FROM isin_cik WHERE status = 'zugeordnet'"
            ).fetchall()
        )
        isin_von.update(
            {
                str(r[0]): str(r[1])
                for r in conn.execute(
                    "SELECT issuer_id, isin FROM grades WHERE issuer_id IS NOT NULL"
                ).fetchall()
            }
        )
        berichte = store.berichte_seit(conn, seit)
        insider = conn.execute(
            "SELECT issuer_id, person_name, rolle, handelstag, veroeffentlicht FROM insider_tx "
            "WHERE art = 'buy' AND offener_markt AND veroeffentlicht > ? "
            "ORDER BY veroeffentlicht DESC LIMIT 200",
            [seit],
        ).fetchall()
        restatements = store.restatements_seit(conn, seit)
        index = conn.execute(
            "SELECT index_id, isin, valid_from, valid_to FROM index_members "
            "WHERE valid_from > ? OR valid_to > ? ORDER BY coalesce(valid_to, valid_from) DESC",
            [seit, seit],
        ).fetchall()
    finally:
        conn.close()

    def titel(isin: str | None) -> dict[str, str]:
        return {"isin": isin or "", "name": str(namen.get(isin, isin or ""))}

    return {
        "seit": None if erster_stand else _tag(seit),
        "tage": [_tag(t) for t in tage[:30]],
        "noten": [
            {
                **titel(isin),
                "note_vorher": alt,
                "note": neu,
                "kategorie_vorher": kat_alt,
                "kategorie": kat_neu,
                "tag": _tag(tag),
                "art": "neu bewertet"
                if alt is None
                else "Notenwechsel"
                if alt != neu
                else "Kategoriewechsel",
            }
            for isin, alt, neu, kat_alt, kat_neu, tag in noten
        ],
        "berichte": [
            {**titel(isin_von.get(i)), "tag": _tag(t), "form": f}
            for i, t, f in berichte
            if isin_von.get(i)
        ],
        "insiderkaeufe": [
            {**titel(isin_von.get(i)), "person": p, "rolle": r, "handelstag": _tag(h)}
            for i, p, r, h, _ in insider
            if isin_von.get(i)
        ],
        "index": [
            {
                **titel(isin),
                "index": idx,
                "art": "aufgenommen" if bis is None or von > seit else "entfernt",
                "tag": _tag(bis or von),
            }
            for idx, isin, von, bis in index
        ],
        "restatements": [
            {**titel(isin_von.get(i)), "werte": n, "tag": _tag(t)}
            for i, n, t in restatements
            if isin_von.get(i)
        ],
    }


# ------------------------------------------------------------------ Historie


def notenverlauf(paths: Paths, isin: str) -> list[dict[str, Any]]:
    conn = store.connect_read(paths.db)
    try:
        rows = conn.execute(
            "SELECT snapshot_date, grade, konfidenz, risiko, kategorie, horizonte_json "
            "FROM grade_snapshots WHERE isin = ? ORDER BY snapshot_date",
            [isin],
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "tag": _tag(t),
            "note": n,
            "konfidenz": k,
            "risiko": r,
            "kategorie": kat,
            "horizonte": {h: v.get("note") for h, v in json.loads(hz).items()} if hz else {},
        }
        for t, n, k, r, kat, hz in rows
    ]


def notenkontrolle(paths: Paths) -> dict[str, Any]:
    """Stand der Notenkontrolle (SPEC 14): Tage mit eingefrorenen Noten und Titel je Note. Die
    Auswertung der Folgerenditen braucht mindestens 12 Monate (`config/scoring.yaml`)."""
    sc = yaml.safe_load((paths.config / "scoring.yaml").read_text("utf-8"))
    conn = store.connect_read(paths.db)
    try:
        r = conn.execute(
            "SELECT count(DISTINCT snapshot_date), min(snapshot_date), max(snapshot_date), "
            "count(DISTINCT isin) FROM grade_snapshots"
        ).fetchone()
        je_note = conn.execute(
            "SELECT grade, count(DISTINCT isin) FROM grade_snapshots GROUP BY 1 ORDER BY 1"
        ).fetchall()
    finally:
        conn.close()
    tage, erster, letzter, titel = r if r else (0, None, None, 0)
    return {
        "tage": tage,
        "erster": _tag(erster) if erster else None,
        "letzter": _tag(letzter) if letzter else None,
        "titel": titel,
        "je_note": dict(je_note),
        "monate_noetig": sc["notenkontrolle"]["monate"],
        "kriterium": sc["notenkontrolle"]["kriterium"],
        "hinweis": "Auswertung je Stufe gegen den Index erst, wenn genug Monate vorliegen "
        "(SPEC 14.4). Bis dahin nur der Stand der eingefrorenen Noten.",
    }


# ------------------------------------------------------------------ Methodik


def methodik(paths: Paths) -> dict[str, Any]:
    """Aktuelle Gewichte, Schwellen und Versionen aus `config/`, dazu das Änderungsprotokoll."""

    def yml(name: str) -> dict[str, Any]:
        data: dict[str, Any] = yaml.safe_load((paths.config / name).read_text("utf-8")) or {}
        return data

    versionen = {}
    for datei in sorted(paths.config.glob("*.yaml")):
        d = yaml.safe_load(datei.read_text("utf-8")) or {}
        v = d.get("version") or d.get("methodology_version")
        if v:
            versionen[datei.name] = str(v)
    sc, hz, mod, lauf = (
        yml("scoring.yaml"),
        yml("horizonte.yaml"),
        yml("models.yaml"),
        yml("run_profiles.yaml"),
    )
    changelog = paths.root / CHANGELOG
    return {
        "methodik_version": methodik_version(paths),
        "versionen": versionen,
        "saeulen_gewichte": sc["saeulen_gewichte"],
        "noten": sc["noten"],
        "kappung": sc["kappung"],
        "konfidenz": sc["konfidenz"],
        "horizonte": {
            k: {"name": v["name"], "momentum_anteil": str(v["momentum_anteil"])}
            for k, v in hz["horizonte"].items()
        },
        "modelle": {"klassen": mod["klassen"], "agenten": mod["agenten"]},
        "grenzen": lauf["grenzen"],
        "stile": lauf["stile"],
        "changelog": changelog.read_text("utf-8") if changelog.exists() else "",
    }
