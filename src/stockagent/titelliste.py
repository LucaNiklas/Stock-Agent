"""Liste aller Aktien mit Filtern (SPEC 9.9 Nr. 3, 13.3, 13.5).

Dashboard und `stockagent run` filtern dieselbe Liste: Stufe, Land, Region, Branche, Größe,
Note, Konfidenz, Risiko, Kategorie, Stil, Handelbarkeit, Datenlage, Beobachtungsliste. Die
Trefferliste entsteht deterministisch aus der Datenbank, ohne Modell (HR-04). Mehrere Werte eines
Filters stehen mit Komma getrennt („DE,AT,CH“) und gelten als „oder“.
"""

from __future__ import annotations

import itertools
import json
import threading
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from stockagent import tiers, tr_checks
from stockagent.core import sektoren
from stockagent.data import store
from stockagent.paths import Paths

MAX_ZEILEN = 500
OHNE_DATEN = "keine strukturierten Daten"


# ------------------------------------------------------------------ Merkliste und Notizen


def _yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text("utf-8")) or {}
    return dict(data)


def yaml_schreiben(path: Path, kopf: str, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join([kopf, yaml.safe_dump(data, sort_keys=True, allow_unicode=True)]), "utf-8"
    )


@dataclass
class Merkliste:
    root: Path

    @property
    def stern_datei(self) -> Path:
        return self.root / "state" / "watchlist.yaml"

    @property
    def notiz_datei(self) -> Path:
        return self.root / "state" / "notes.yaml"

    def sterne(self) -> set[str]:
        return set(_yaml(self.stern_datei).get("isins", []))

    def stern(self, isin: str, an: bool) -> None:
        s = self.sterne()
        s = s | {isin} if an else s - {isin}
        yaml_schreiben(self.stern_datei, "# Beobachtungsliste (Dashboard)", {"isins": sorted(s)})

    def notizen(self) -> dict[str, str]:
        return {str(k): str(v) for k, v in _yaml(self.notiz_datei).items()}

    def notiz(self, isin: str, text: str) -> None:
        n = self.notizen()
        if text.strip():
            n[isin] = text.strip()
        else:
            n.pop(isin, None)
        yaml_schreiben(self.notiz_datei, "# Notizen je Titel (Dashboard)", n)


# ------------------------------------------------------------------ Zeilen


@dataclass(frozen=True)
class Zeile:
    isin: str
    name: str
    land: str
    region: str
    art: str
    tier: int
    branche: str
    unterbranche: str
    groesse: str
    note: str
    konfidenz: str
    risiko: str
    kategorie: str
    score: str
    tr: str
    stern: bool
    datenlage: str
    # Note, Kategorie und Gesamtwert je Anlagehorizont (ADR 0011)
    horizonte: dict[str, dict[str, str]] = field(default_factory=dict)
    # Insider-Signal (Bauschritt 9): Käufe, Verkäufe, kein Signal oder leer (nicht bewertet)
    insider: str = ""
    # Bauschritt 11: Säulen (Perzentil) für Stile, Dividendenrendite, Tag der Bewertung, LEI da?
    saeulen: dict[str, str] = field(default_factory=dict)
    dividendenrendite: str = ""
    bewertet_am: str = ""
    lei: bool = False


def _insider_text(d: dict[str, Any] | None) -> str:
    """Kurzform des Insider-Signals für den Filter (50 = neutral, SPEC 3.8)."""
    if d is None:
        return ""
    if d.get("saeule") is None:
        return "kein Signal"
    wert = Decimal(str(d["saeule"]))
    return "Käufe" if wert > 50 else "Verkäufe" if wert < 50 else "kein Signal"


class Daten:
    """Liste aller Aktien, einmal geladen und nach jedem Bewerten neu."""

    def __init__(self, paths: Paths) -> None:
        self.paths = paths
        self.lock = threading.Lock()
        self.zeilen: list[Zeile] = []
        self.stand = ""
        h = yaml.safe_load((paths.config / "horizonte.yaml").read_text("utf-8"))
        self.horizont_standard = str(h["standard"])
        self.horizont_namen = {k: str(v["name"]) for k, v in h["horizonte"].items()}
        self.horizont_info = {
            k: {
                "name": str(v["name"]),
                "momentum_anteil": str(v["momentum_anteil"]),
                "mindest": v.get("kategorie_momentum_mindest"),
            }
            for k, v in h["horizonte"].items()
        }
        lauf = yaml.safe_load((paths.config / "run_profiles.yaml").read_text("utf-8"))
        self.stile: dict[str, dict[str, Any]] = dict(lauf["stile"])
        self.neu_laden()

    def neu_laden(self) -> None:
        cfg_sec = yaml.safe_load((self.paths.config / "sectors.yaml").read_text("utf-8"))
        cfg_sc = yaml.safe_load((self.paths.config / "scoring.yaml").read_text("utf-8"))
        regionen = cfg_sc["vergleichsgruppe"]["regionen"]
        merk = Merkliste(self.paths.root)
        sterne = merk.sterne()
        checks = tr_checks.load(self.paths.tr_checks)
        stufen = tiers.stufen_aller(self.paths)
        conn = store.connect(self.paths.db)
        try:
            rows = conn.execute(
                "SELECT l.isin, l.name, l.country, l.is_receipt, i.sector_sic, m.cik, l.lei "
                "FROM listings l LEFT JOIN isin_cik m ON m.isin = l.isin "
                "AND m.status = 'zugeordnet' "
                "LEFT JOIN issuers i ON i.issuer_id = 'sec:' || m.cik WHERE l.listed "
                "ORDER BY l.name"
            ).fetchall()
            grades = {g.isin: g for g in store.load_grades(conn)}
            stand = conn.execute("SELECT max(computed_at) FROM grades").fetchone()
            dividenden = dict(
                conn.execute(
                    "SELECT m.issuer_id, arg_max(m.value, m.period_end) FROM metrics m JOIN "
                    "(SELECT issuer_id, arg_max(run_id, computed_at) AS run_id FROM metric_runs "
                    "GROUP BY issuer_id) r ON r.run_id = m.run_id "
                    "WHERE m.metric_id = 'dividend_yield' AND m.statistik = 'aktuell' "
                    "GROUP BY m.issuer_id"
                ).fetchall()
            )
        finally:
            conn.close()
        zeilen = []
        for isin, name, land, receipt, sic, cik, lei in rows:
            b = sektoren.branche(int(sic) if sic and str(sic).isdigit() else None, cfg_sec)
            g = grades.get(isin)
            c = checks.get(isin)
            det = json.loads(g.detail_json or "{}") if g else {}
            hz = det.get("horizonte") or {}
            issuer = g.issuer_id if g and g.issuer_id else (f"sec:{cik}" if cik else None)
            datenlage = (
                "SEC" if cik else "ESEF" if issuer and issuer.startswith("lei:") else OHNE_DATEN
            )
            zeilen.append(
                Zeile(
                    isin=isin,
                    name=name,
                    land=land or "",
                    region=sektoren.region(land, regionen) or "",
                    art="Hinterlegungsschein" if receipt else "Aktie",
                    tier=stufen.get(isin, (4, []))[0],
                    branche=b.haupt_name if b else "",
                    unterbranche=b.unter_name if b else "",
                    groesse=(g.groessenklasse or "") if g else "",
                    note=g.grade if g else "",
                    konfidenz=(g.konfidenz or "") if g else "",
                    risiko=(g.risiko or "") if g else "",
                    kategorie=(g.kategorie or "") if g else "",
                    score=str(g.score) if g and g.score is not None else "",
                    tr=c.status.value if c else "ungeprueft",
                    stern=isin in sterne,
                    datenlage=datenlage,
                    horizonte={
                        h: {
                            "note": str(v.get("note") or ""),
                            "kategorie": str(v.get("kategorie") or ""),
                            "score": str(v.get("score") or ""),
                        }
                        for h, v in hz.items()
                    },
                    insider=_insider_text(det.get("insider")),
                    saeulen={
                        k: str(v) for k, v in (det.get("saeulen") or {}).items() if v is not None
                    },
                    dividendenrendite=str(dividenden.get(issuer) or "") if issuer else "",
                    bewertet_am=f"{g.computed_at:%Y-%m-%d}" if g else "",
                    lei=bool(lei),
                )
            )
        with self.lock:
            self.zeilen = zeilen
            self.stand = f"{stand[0]:%d.%m.%Y %H:%M}" if stand and stand[0] else ""


# ------------------------------------------------------------------ Filtern

FILTER = (
    "tier",
    "land",
    "region",
    "branche",
    "unterbranche",
    "groesse",
    "note",
    "konfidenz",
    "risiko",
    "kategorie",
    "tr",
    "datenlage",
    "art",
    "insider",
)
# Filter, die erst nach dem Bewerten feststehen (Note und Säulen)
NACH_BEWERTUNG = ("note", "konfidenz", "risiko", "kategorie", "insider", "stil", "groesse")


def ansicht(z: Zeile, horizont: str) -> Zeile:
    """Zeile mit Note, Kategorie und Gesamtwert des gewählten Horizonts. Ältere Bewertungen
    ohne Horizonte behalten die Hauptnote."""
    h = z.horizonte.get(horizont)
    if not h or z.note == "N":
        return z
    return replace(z, note=h["note"], kategorie=h["kategorie"], score=h["score"])


def wert(z: Zeile) -> Decimal:
    try:
        return Decimal(z.score)
    except InvalidOperation:
        return Decimal(-1)


def _dec(s: str) -> Decimal | None:
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def stil_erfuellt(z: Zeile, stil: str, stile: dict[str, dict[str, Any]]) -> bool:
    """Stil aus `config/run_profiles.yaml`. Ohne Note oder Kennzahl nicht erfüllt."""
    s = stile.get(stil)
    if not s or s.get("gebaut") is False:
        return False
    if "saeule" in s:
        v = _dec(z.saeulen.get(str(s["saeule"]), ""))
        return v is not None and v >= Decimal(str(s["mindest"]))
    if "kennzahl" in s:
        v = _dec(z.dividendenrendite) if s["kennzahl"] == "dividend_yield" else None
        return v is not None and v >= Decimal(str(s["mindest"]))
    if "insider" in s:
        return bool(z.insider == s["insider"])
    return False


def passt(
    z: Zeile,
    f: dict[str, str],
    stile: dict[str, dict[str, Any]],
    ohne: tuple[str, ...] = (),
) -> bool:
    """Erfüllt die Zeile alle Filter? `ohne`: diese Filter auslassen."""
    if f.get("beobachtung") == "dazu" and z.stern:
        return True  # Beobachtungsliste zusätzlich zu den Treffern (SPEC 9.7)
    for k in FILTER:
        if k in ohne or not f.get(k):
            continue
        if str(getattr(z, k)) not in f[k].split(","):
            return False
    if f.get("isin") and "isin" not in ohne and z.isin not in f["isin"].split(","):
        return False
    stile_ = f["stil"].split(",") if f.get("stil") and "stil" not in ohne else []
    if not all(stil_erfuellt(z, s, stile) for s in stile_):
        return False
    if f.get("stern") == "1" and not z.stern:
        return False
    if f.get("bewertet") == "1" and not z.note:
        return False
    q = f.get("q", "").strip().lower()
    return not q or q in z.name.lower() or q.upper() == z.isin


def horizont_von(daten: Daten, f: dict[str, str]) -> str:
    h = f.get("horizont") or daten.horizont_standard
    return h if h in daten.horizont_namen else daten.horizont_standard


def alle_im_horizont(daten: Daten, f: dict[str, str]) -> list[Zeile]:
    horizont = horizont_von(daten, f)
    with daten.lock:
        return [ansicht(z, horizont) for z in daten.zeilen]


def treffer(daten: Daten, f: dict[str, str], ohne: tuple[str, ...] = ()) -> list[Zeile]:
    return [z for z in alle_im_horizont(daten, f) if passt(z, f, daten.stile, ohne)]


def liste(daten: Daten, f: dict[str, str]) -> dict[str, Any]:
    horizont = horizont_von(daten, f)
    alle = alle_im_horizont(daten, f)
    gefunden = [z for z in alle if passt(z, f, daten.stile)]
    if f.get("sortierung") == "wert":
        # Bewertete zuerst, nach Gesamtwert des Horizonts absteigend (nur Anzeige, kein Rang)
        gefunden.sort(key=wert, reverse=True)
    facetten: dict[str, list[tuple[str, int]]] = {}
    for k in FILTER:
        zaehler = Counter(str(getattr(z, k)) for z in alle if passt(z, f, daten.stile, (k,)))
        facetten[k] = sorted(zaehler.items(), key=lambda x: (-x[1], x[0]))
    bewertet = sum(1 for z in alle if z.note and z.note != "N")
    return {
        "anzahl": len(gefunden),
        "gesamt": len(alle),
        "bewertet": bewertet,
        "stand": daten.stand,
        "zeilen": [asdict(z) for z in gefunden[:MAX_ZEILEN]],
        "facetten": facetten,
        "horizont": horizont,
        "horizonte": daten.horizont_info,
        "stile": {k: str(v["name"]) for k, v in daten.stile.items() if v.get("gebaut", True)},
    }


# ------------------------------------------------------------------ Lockern bei null Treffern


def lockerungen(daten: Daten, f: dict[str, str]) -> list[dict[str, Any]]:
    """Mögliche Lockerungen eines Filters mit Trefferzahl (SPEC 9.9 Nr. 2). Je Filter eine
    Stufe weiter: Tier n bis n+1, Note bis zur nächsten, Land zur Region, Unterbranche zur
    Hauptbranche, sonst Filter weglassen."""
    cfg_sc = yaml.safe_load((daten.paths.config / "scoring.yaml").read_text("utf-8"))
    regionen = cfg_sc["vergleichsgruppe"]["regionen"]
    alle = alle_im_horizont(daten, f)
    kandidaten: list[tuple[str, dict[str, str]]] = []

    def weiter(liste_: str, werte: str) -> str | None:
        hoechst = max(werte.split(","))
        naechste = dict(itertools.pairwise(liste_)).get(hoechst)
        return ",".join(x for x in liste_ if x <= naechste) if naechste else None

    for schluessel, reihe, text in (("tier", "1234", "Tier"), ("note", "ABCDE", "Note")):
        if f.get(schluessel) and (neu := weiter(reihe, f[schluessel])):
            kandidaten.append((f"{text} {neu.replace(',', ', ')}", {**f, schluessel: neu}))
    if f.get("land"):
        laender = f["land"].split(",")
        region = {sektoren.region(x, regionen) for x in laender}
        if len(region) == 1 and (r := region.pop()):
            ohne_land = {k: v for k, v in f.items() if k != "land"}
            kandidaten.append((f"ganze Region {r}", {**ohne_land, "region": r}))
    if f.get("unterbranche"):
        with daten.lock:
            haupt = {z.branche for z in daten.zeilen if z.unterbranche in f["unterbranche"]}
        ohne_unter = {k: v for k, v in f.items() if k != "unterbranche"}
        if len(haupt) == 1:
            h = haupt.pop()
            kandidaten.append((f"ganze Branche {h}", {**ohne_unter, "branche": h}))
    for k in ("groesse", "kategorie", "stil", "tr", "konfidenz", "risiko", "region", "branche"):
        if f.get(k):
            kandidaten.append((f"ohne Filter {k}", {kk: v for kk, v in f.items() if kk != k}))
    out: list[dict[str, Any]] = []
    for text, gelockert in kandidaten:
        anzahl = sum(1 for z in alle if passt(z, gelockert, daten.stile))
        if anzahl:
            out.append({"text": text, "filter": gelockert, "anzahl": anzahl})
    out.sort(key=lambda x: int(x["anzahl"]))
    return out


# ------------------------------------------------------------------ Karte Branche mal Land


def karte(daten: Daten, f: dict[str, str]) -> list[dict[str, Any]]:
    """Anzahl Titel und Anzahl „Attraktiv“ je Branche und Land, unter allen übrigen Filtern
    (SPEC 13.3 Karte). Die Fläche zeichnet das Dashboard, die Farbe ist der Anteil Attraktiv."""
    zellen: dict[tuple[str, str], list[int]] = {}
    for z in treffer(daten, f, ohne=("branche", "unterbranche", "land", "region")):
        zelle = zellen.setdefault((z.branche or "ohne Branchencode", z.land or "?"), [0, 0, 0])
        zelle[0] += 1
        if z.note and z.note != "N":
            zelle[1] += 1
        if z.kategorie == "Attraktiv":
            zelle[2] += 1
    branchen: dict[str, dict[str, Any]] = {}
    for (b, land), (n, bewertet, attraktiv) in zellen.items():
        eintrag = branchen.setdefault(b, {"branche": b, "anzahl": 0, "laender": []})
        eintrag["laender"].append(
            {"land": land, "anzahl": n, "bewertet": bewertet, "attraktiv": attraktiv}
        )
    for e in branchen.values():
        e["laender"].sort(key=lambda x: -x["anzahl"])
        e["anzahl"] = sum(x["anzahl"] for x in e["laender"])
    return sorted(branchen.values(), key=lambda x: -x["anzahl"])
