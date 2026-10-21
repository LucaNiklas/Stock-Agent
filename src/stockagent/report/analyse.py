"""Finanzieller Überblick einer Tiefenanalyse mit 14 Abschnitten (SPEC 12.3, HR-08, HR-10, HR-16).

Der Bericht entsteht nur aus Python-Daten über die Vorlagen `analysis.md.j2` und
`analysis.html.j2`. Freitext der Agenten steht nur in These, Befunden, Gegenposition und
Erwiderung, und nur aus geprüften Claims (Status `verified`). Platzhalter ersetzt der Renderer
durch die gespeicherten Werte (HR-01). Abschnitte ohne Inhalt sagen „nicht anwendbar“ mit Grund.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from importlib.resources import files
from typing import TYPE_CHECKING, Any

import yaml
from jinja2 import Environment, StrictUndefined

from stockagent import tr_checks
from stockagent.agents import eingaben
from stockagent.core.anzeige import formatiere
from stockagent.data import store
from stockagent.paths import Paths
from stockagent.platzhalter import Werte

if TYPE_CHECKING:
    from stockagent.orchestrator import Zustand

KENNZAHLEN_TABELLE = (
    "gross_margin",
    "ebit_margin",
    "fcf_margin",
    "roic",
    "roe",
    "gp_to_assets",
    "revenue_cagr_5y",
    "fcf",
    "fcf_conversion",
    "net_debt_to_ebitda",
    "interest_coverage",
    "equity_ratio",
    "share_count_change_3y",
    "pe",
    "ev_ebit",
    "fcf_yield",
)
ERTRAGSQUALITAET = (
    "piotroski_f_score",
    "altman_z_double_prime",
    "beneish_m_score",
    "sloan_accruals",
    "fcf_conversion",
    "ocf_to_net_income",
)
THEMEN_NAME = {
    "geschaeftsmodell": "Geschäftsmodell",
    "wettbewerbsvorteil": "Wettbewerbsvorteil",
    "segmente": "Segmente",
    "kundenkonzentration": "Kundenkonzentration",
    "risikofaktoren": "Risikofaktoren",
    "management_anreize": "Management und Anreize",
    "kapitalallokation": "Kapitalallokation",
    "bilanzpolitik": "Bilanzpolitik",
    "pruefungsschwerpunkte": "Prüfungsschwerpunkte",
}
BEWERTUNG = (
    "wacc",
    "implied_growth",
    "growth_gap",
    "dcf_bear",
    "dcf_base",
    "dcf_bull",
    "margin_of_safety",
    "ev_ebit",
    "pe",
    "fcf_yield",
    "ev_ebit_normalized",
)

PRUEFUNGEN = [
    "Datenqualität DQ-01 bis DQ-08 (Bilanzgleichung, Summen, zweiter Weg, Ausreißer)",
    "Prüfpunkte CP-01 bis CP-07 in jeder Rechnung (INC-15)",
    "Schranken je Agentenantwort: Schema, Zahlen, Beleg, Zitat, Formulierung, Konsistenz",
    "J1 blinde Nachrechnung jeder zitierten Kennzahl (INC-01)",
    "J2 Belegprüfung jeder Aussage mit Dokumentstelle (INC-11)",
]


def _cfg(paths: Paths, name: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((paths.config / name).read_text("utf-8"))
    return data


def _claim(c: dict[str, Any], w: Werte, ordner: dict[str, str]) -> dict[str, Any]:
    belege = []
    for e in c.get("evidence", []):
        if e.get("doc_hash"):
            belege.append(
                {
                    "art": "dokument",
                    "seite": e["page"],
                    "zitat": e.get("quote") or "",
                    "doc": e["doc_hash"][:19],
                    "datei": f"{ordner.get(e['doc_hash'], '')}/seite_{e['page']:03d}.txt",
                }
            )
        elif e.get("metric_ref"):
            belege.append({"art": "kennzahl", "ref": e["metric_ref"]})
    return {"text": w.ersetze(c["text"]), "belege": belege, "id": c.get("schluessel", "")}


def _wert(w: Werte, ref: str) -> str:
    return w.anzeige(ref) if w.hole(ref) else "–"


def kontext(paths: Paths, z: Zustand, ent: dict[str, Any]) -> dict[str, Any]:
    conn = store.connect_read(paths.db)
    try:
        w = Werte.laden(conn, z.issuer_id, _cfg(paths, "metrics.yaml"))
        listing = conn.execute(
            "SELECT lei, currency FROM listings WHERE isin = ?", [z.isin]
        ).fetchone()
        lauf = store.load_metric_run(conn, z.issuer_id)
        flags = store.load_dq_flags(conn, z.issuer_id)
        rows = store.load_metrics(conn, z.issuer_id)
        vorher = conn.execute(
            "SELECT snapshot_date, grade, kategorie FROM grade_snapshots WHERE isin = ? "
            "ORDER BY snapshot_date DESC LIMIT 2",
            [z.isin],
        ).fetchall()
        quellen = conn.execute(
            "SELECT doc_type, period_end, source_url, doc_hash FROM documents "
            "WHERE issuer_id = ? AND doc_hash IS NOT NULL AND doc_type <> 'FORM4' "
            "ORDER BY period_end DESC",
            [z.issuer_id],
        ).fetchall()
        grade = store.load_grade(conn, z.isin)
    finally:
        conn.close()
    status = ent["claims"]
    ordner = {d["doc_hash"]: d["ordner"] for d in z.dokumente}

    def geprueft(slot: str, ids: list[str] | None = None) -> list[dict[str, Any]]:
        antwort = eingaben.ausgabe(paths, z, slot) or {}
        out = []
        for c in antwort.get("claims", []):
            key = f"{slot}:{c['claim_id']}"
            if ids is not None and c["claim_id"] not in ids:
                continue
            if status.get(key, {}).get("status") == "verified":
                out.append(_claim({**c, "schluessel": key}, w, ordner))
        return out

    note = ent["note"]
    tr = tr_checks.load(paths.tr_checks).get(z.isin)
    defs = w.defs
    jahre = sorted({r.period_end.year for r in rows if r.statistik == "wert"})[-10:]

    def zeile(mid: str) -> dict[str, Any]:
        perz = next(
            (r for r in note.get("raenge", []) if r["kennzahl"] == mid and r.get("perzentil")),
            None,
        )
        return {
            "name": defs[mid]["name"],
            "jahre": [_wert(w, f"{mid}@{j}") for j in jahre],
            "ttm": _wert(w, f"{mid}@ttm"),
            "aktuell": _wert(w, f"{mid}@aktuell"),
            "gruppe": formatiere(Decimal(perz["perzentil"]), "ganzzahl", 0) if perz else "–",
        }

    a3 = eingaben.ausgabe(paths, z, "A3")
    a4 = eingaben.ausgabe(paths, z, "A4")
    a6 = eingaben.ausgabe(paths, z, "A6")
    a7 = eingaben.ausgabe(paths, z, "A7")
    a3e = eingaben.ausgabe(paths, z, "A3E")
    # Insider (SPEC 12.3 Abschnitt 9): Geschäfte und Signal aus Python, Einordnung von A6
    ins = (json.loads(grade.detail_json or "{}").get("insider") if grade else None) or {}
    insider_abschnitt = {
        "saeule": ins.get("saeule"),
        "grund": ins.get("grund"),
        "geschaefte": ins.get("geschaefte", []),
        "einordnung": (a6 or {}).get("einordnung"),
        "befunde": [
            {"muster": b["muster"], "claims": geprueft("A6", b["claim_ids"])}
            for b in (a6 or {}).get("befunde", [])
        ],
    }
    a9 = eingaben.ausgabe(paths, z, "A9")
    themen = []
    for t in (a4 or {}).get("themen", []):
        themen.append(
            {
                "thema": THEMEN_NAME[t["thema"]],
                "schluessel": t["thema"],
                "einordnung": t["einordnung"],
                "claims": geprueft("A4", t["claim_ids"]),
            }
        )
    risiken = []
    for i, r in enumerate((a7 or {}).get("risiken", []), start=1):
        antwort = next((e for e in (a3e or {}).get("erwiderungen", []) if e["risiko"] == i), None)
        risiken.append(
            {
                "titel": w.ersetze(r["titel"]),
                "fruehindikator": w.ersetze(r["fruehindikator"]),
                "claims": geprueft("A7", r["claim_ids"]),
                "offen": antwort is None or antwort["offen"],
                "erwiderung": geprueft("A3E", antwort["claim_ids"]) if antwort else [],
            }
        )

    # Bewertung: Standard-Szenarien und Wahl von A5
    a5 = ent["a5"]
    a5_werte = {
        s: (
            formatiere(Decimal(v["wert"]), "kurs", 2, w.waehrung)
            if v["wert"]
            else f"unbekannt ({v['grund']})"
        )
        for s, v in a5["werte"].items()
    }
    sens: list[dict[str, str]] = []
    base_row = next(
        (r for r in rows if r.metric_id == "dcf_base" and r.statistik == "aktuell"), None
    )
    if base_row and base_row.calc_trace_json:
        for s in json.loads(base_row.calc_trace_json)["schritte"]:
            if s["name"].startswith("sens_wacc_"):
                _, _, dw, _, dg = s["name"].split("_")
                sens.append(
                    {
                        "wacc": formatiere(Decimal(dw), "punkte", 1),
                        "g": formatiere(Decimal(dg), "punkte", 1),
                        "wert": formatiere(Decimal(s["ergebnis"]), "kurs", 2),
                    }
                )

    ungereimt = [
        {"id": "INC-15", "text": f"{r.metric_id} ({r.period_end}): {r.ungereimtheit}"}
        for r in rows
        if r.ungereimtheit and r.period_end == (lauf[2] if lauf else None)
    ]
    ungereimt += [
        {"id": f.check_id, "text": f"{f.severity}: {f.detail}"}
        for f in flags
        if f.severity in ("warnung", "stopp")
    ]
    ungereimt += [
        {"id": "INC-01", "text": f"J1 {r}: nachgerechnet {v['j1']}, gespeichert {v['gespeichert']}"}
        for r, v in ent["j1"].items()
        if v["urteil"] == "mismatch"
    ]
    entfernt = []
    for a in z.auftraege:
        if a.status != "angenommen":
            continue
        daten = json.loads((paths.root / a.ausgabe).read_text("utf-8"))
        for r in daten["removed_claims"]:
            entfernt.append({"auftrag": a.id, "grund": r["reason"]})
        for cid, grund in daten["abgelehnt"].items():
            entfernt.append({"auftrag": a.id, "grund": f"{cid}: {grund}"})
            ungereimt.append({"id": "INC-14", "text": f"{a.id} {cid}: {grund}"})
    for key, s in status.items():
        if s["status"] == "rejected" and any(g.startswith("J2") for g in s["gruende"]):
            ungereimt.append({"id": "INC-11", "text": f"{key}: {'; '.join(s['gruende'])}"})

    # Nur Vermerke zu Kennzahlen, die der Bericht zeigt oder die Note nutzt (Scorecard)
    genutzt = {r["kennzahl"] for r in ent["note"].get("raenge", [])}.union(
        KENNZAHLEN_TABELLE, ERTRAGSQUALITAET, BEWERTUNG
    )
    vermerke: dict[str, set[str]] = {}
    for r in rows:
        if r.metric_id not in genutzt:
            continue
        if r.period_end == (lauf[2] if lauf else None) and r.statistik == "wert":
            for v in r.vermerke:
                vermerke.setdefault(v, set()).add(r.metric_id)
    kurs = ent.get("kurs")
    if kurs:
        kurs = {**kurs, "wert": formatiere(Decimal(kurs["wert"]), "kurs", 2, kurs["waehrung"])}
    j1_zahl = dict(Counter(v["urteil"] for v in ent["j1"].values()))
    zaehler = dict(Counter(s["status"] for s in status.values()))

    return {
        "kopf": {
            "name": z.name,
            "isin": z.isin,
            "lei": (listing[0] if listing else None) or "nicht vorhanden",
            "tr": tr.status.value if tr else "ungeprüft",
            "scorecard": note.get("scorecard") or "–",
            "standard": "US-GAAP",
            "berichtswaehrung": w.waehrung or "unbekannt",
            "kurswaehrung": (ent.get("kurs") or {}).get("waehrung") or "unbekannt",
            "datenstand": f"{lauf[1]:%d.%m.%Y}" if lauf else "unbekannt",
            "stichtag": f"{lauf[2]:%d.%m.%Y}" if lauf and lauf[2] else "unbekannt",
            "run_id": z.run_id,
            "methodik": lauf[3] if lauf else "unbekannt",
            "register": "sha256:"
            + hashlib.sha256((paths.config / "metrics.yaml").read_bytes()).hexdigest()[:16],
            "erstellt": f"{datetime.now(UTC):%d.%m.%Y %H:%M} UTC",
        },
        "urteil": {
            "note": note.get("note"),
            "gesamtwert": formatiere(Decimal(note["gesamtwert"]), "faktor", 1)
            if note.get("gesamtwert")
            else "–",
            "konfidenz": note.get("konfidenz") or "–",
            "risiko": note.get("risiko") or "–",
            "kategorie": ent["kategorie"],
            "deterministisch": ent["kategorie_deterministisch"],
            "uebergaenge": ent["uebergaenge"],
            "vergleichsgruppe": f"{note.get('gruppe_titel', 0)} Titel, "
            f"{note.get('vergleichsgruppe')}",
            "vorher": f"Note {vorher[1][1]} am {vorher[1][0]:%d.%m.%Y}"
            if len(vorher) > 1
            else None,
            "grund": note.get("grund"),
        },
        "these": {
            "text": w.ersetze(a9["these"]) if a9 else None,
            "claims": [c for c in (a9 or {}).get("these_claims", [])],
        },
        "geschaeftsmodell": [
            t
            for t in themen
            if t["schluessel"] in ("geschaeftsmodell", "segmente", "kundenkonzentration")
        ],
        "kennzahlen": {
            "jahre": jahre,
            "zeilen": [zeile(m) for m in KENNZAHLEN_TABELLE if m in defs],
        },
        "ertragsqualitaet": {
            "werte": [
                {"name": defs[m]["name"], "wert": _wert(w, f"{m}@{jahre[-1]}") if jahre else "–"}
                for m in ERTRAGSQUALITAET
                if m in defs
            ],
            "einordnung": (a3 or {}).get("ertragsqualitaet", "unknown"),
            "claims": geprueft("A3"),
        },
        "bewertung": {
            "kennzahlen": [
                {"name": defs[m]["name"], "wert": _wert(w, f"{m}@aktuell")}
                for m in BEWERTUNG
                if m in defs
            ],
            "a5_wahl": a5["wahl"],
            "a5_werte": a5_werte,
            "a5_korrekturen": a5["korrekturen"],
            "a5_claims": geprueft("A5"),
            "sensitivitaet": sens,
            "kurs": kurs,
        },
        "anpassungen": [
            f"{text} ({', '.join(sorted(ids))})" for text, ids in sorted(vermerke.items())
        ],
        "themen": themen,
        "insider": insider_abschnitt,
        "gegenposition": {
            "risiken": risiken,
            "pre_mortem": w.ersetze(a7["pre_mortem"]) if a7 else None,
        },
        "ungereimtheiten": ungereimt,
        "pruefungen": PRUEFUNGEN,
        "protokoll": {
            "auftraege": [
                {
                    "id": a.id,
                    "agent": a.agent,
                    "status": a.status,
                    "versuche": a.versuche,
                    "fehler": len(a.fehler),
                }
                for a in z.auftraege
            ],
            "j1": j1_zahl,
            "claims": zaehler,
            "entfernt": entfernt,
        },
        "grenzen": {
            "lauf": z.grenzen,
            "konfidenz": note.get("konfidenz_gruende", []),
            "luecken": sorted(
                {
                    f"{r.metric_id}: {r.grund}"
                    for r in rows
                    if r.statistik == "wert"
                    and r.value is None
                    and r.period_end == (lauf[2] if lauf else None)
                }
            ),
            "quellen": [
                *[
                    {
                        "typ": q[0],
                        "periode": f"{q[1]:%d.%m.%Y}" if q[1] else "",
                        "url": q[2],
                        "hash": q[3][:19],
                    }
                    for q in quellen
                ],
                {"typ": "XBRL Company Facts", "periode": "", "url": "data.sec.gov", "hash": ""},
            ],
        },
    }


def erzeugen(paths: Paths, z: Zustand, ent: dict[str, Any]) -> tuple[str, str]:
    ctx = kontext(paths, z, ent)
    vorlagen = files("stockagent.report").joinpath("templates")
    md = Environment(undefined=StrictUndefined, autoescape=False, trim_blocks=True)
    html = Environment(undefined=StrictUndefined, autoescape=True, trim_blocks=True)
    text_md = md.from_string(vorlagen.joinpath("analysis.md.j2").read_text("utf-8")).render(**ctx)
    text_html = html.from_string(vorlagen.joinpath("analysis.html.j2").read_text("utf-8")).render(
        **ctx
    )
    return text_md, text_html
