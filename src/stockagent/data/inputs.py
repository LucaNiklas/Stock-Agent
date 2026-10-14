"""Eingangswerte der Kennzahlen aus der Datenbank (Abteilung Berechnung, SPEC 8.1).

Liest über `pit_query` zum Zeitpunkt `as_of` (HR-07), ordnet Konzepte je Periode zu
(`config/concept_map.yaml`) und baut daraus `core.reihen.Reihen`: je interner Größe die Werte
an den Geschäftsjahresenden (Stände) oder über das Geschäftsjahr (Ströme). Dazu die
Split-Ereignisse aus den Deckblatt-Meldungen (DQ-08). Reine Auswahl, keine Arithmetik.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from itertools import pairwise
from typing import Any

import duckdb

from stockagent.core import dq
from stockagent.core.calc import Eingabe
from stockagent.core.reihen import Reihen, Split
from stockagent.data import concepts, quality, store


def eingabe(f: store.StoredFact) -> Eingabe:
    return Eingabe(
        f.value, f.quelle, f.unit, f.period_end, f.currency, f.period_start, f.published_at
    )


def splits(
    conn: duckdb.DuckDBPyConnection,
    issuer_id: str,
    as_of: datetime,
    concept: str,
    toleranz: Decimal,
) -> tuple[Split, ...]:
    """Splits aus der Aktienanzahl vom Deckblatt, je Stichtag wie damals gemeldet."""
    reihe = sorted(
        (
            f
            for f in store.pit_query(
                conn, as_of=as_of, issuer_id=issuer_id, concepts=[concept], fassung="erste"
            )
            if f.period_start is None and f.unit == "shares"
        ),
        key=lambda f: f.period_end,
    )
    out = []
    for vorher, nachher in pairwise(reihe):
        v = dq.split_verdacht(issuer_id, eingabe(vorher), eingabe(nachher), toleranz)
        if v.faktor is not None and v.verhaeltnis is not None:
            out.append(Split(nachher.published_at, v.faktor, v.verhaeltnis))
    return tuple(out)


def _kurs_eingabe(k: store.PriceRow, stichtag: date) -> Eingabe:
    """Schlusskurs als Eingabe für den Stichtag. Der tatsächliche Handelstag steht in der Quelle."""
    return Eingabe(
        k.close,
        f"Yahoo {k.symbol} Schlusskurs {k.date.isoformat()}",
        "per_share",
        stichtag,
        k.currency,
    )


def _fx_eingabe(f: store.FxRate, stichtag: date) -> Eingabe:
    return Eingabe(
        f.per_eur,
        f"EZB-Referenzkurs {f.currency} je EUR {f.date.isoformat()} (Rohdatei {f.raw_sha256[:12]})",
        "fx",
        stichtag,
    )


def _fx_waehrungen(*waehrungen: str | None) -> list[str]:
    """Währungen, für die ein EZB-Referenzkurs gebraucht wird (alle außer dem Euro)."""
    return sorted({w for w in waehrungen if w and w != "EUR"})


def kurse(
    conn: duckdb.DuckDBPyConnection,
    isin: str | None,
    stichtage: list[date],
    berichtswaehrung: str | None,
    unterwaehrungen: dict[str, str],
    max_abstand_tage: int,
) -> tuple[dict[str, dict[date, Eingabe]], dict[str, str]]:
    """Kurs je Stichtag (letzter Schlusskurs bis zum Stichtag, höchstens `max_abstand_tage`
    davor) und die Referenzkurse der EZB, die für die Umrechnung nötig sind. Dazu Gründe für
    Lücken. Reine Auswahl, keine Arithmetik."""
    werte: dict[str, dict[date, Eingabe]] = {"kurs": {}}
    if isin is None:
        return werte, {"kurs": "keine ISIN zum Emittenten bekannt"}
    if store.listing_is_receipt(conn, isin):
        return werte, {
            "kurs": "Hinterlegungsschein, Depotverhältnis zur Stammaktie fehlt (SPEC 5.2 Nr. 11)"
        }
    sym = store.load_price_symbol(conn, isin)
    if sym is None or sym.symbol is None:
        return werte, {"kurs": f"keine Kurse geladen (stockagent prices update -i {isin})"}
    for t in stichtage:
        k = store.price_on_or_before(conn, isin, t)
        if k is None or dq.kurs_veraltet(k.date, t, max_abstand_tage):
            continue
        werte["kurs"][t] = _kurs_eingabe(k, t)
        haupt = unterwaehrungen.get(str(k.currency), str(k.currency))
        for w in _fx_waehrungen(haupt, berichtswaehrung):
            f = store.fx_on_or_before(conn, str(w), k.date)
            if f is not None:
                werte.setdefault(f"fx_{w}", {})[t] = _fx_eingabe(f, t)
    luecken = {} if werte["kurs"] else {"kurs": "keine Kurse an den Geschäftsjahresenden"}
    return werte, luecken


def reihen(
    conn: duckdb.DuckDBPyConnection,
    issuer_id: str,
    as_of: datetime,
    cmap: dict[str, Any],
    quality_cfg: dict[str, Any],
    max_jahre: int = 11,
    *,
    isin: str | None = None,
    kurs_cfg: dict[str, Any] | None = None,
) -> Reihen:
    """Jahresreihen aller internen Größen aus `cmap['us-gaap']` für bis zu `max_jahre` Jahre.
    Mit `isin` und `kurs_cfg` (Abschnitt `kurse` aus metrics.yaml plus Unterwährungen) auch
    Schlusskurse und Wechselkurse an den Stichtagen."""
    facts = store.pit_query(conn, as_of=as_of, issuer_id=issuer_id)
    stichtage = quality.jahresstichtage(facts)[:max_jahre]
    werte: dict[str, dict[Any, Eingabe]] = {}
    for name, liste in cmap["us-gaap"].items():
        je_tag = {}
        for (start, ende), f in concepts.resolve(facts, liste).items():
            if ende not in stichtage:
                continue
            if start is not None and not dq.periode_passt(start, ende, "FY"):
                continue
            je_tag[ende] = eingabe(f)
        werte[name] = je_tag
    luecken: dict[str, str] = {}
    parameter: dict[str, Any] = {}
    if kurs_cfg is not None:
        umsatz = next(iter(werte.get("revenue", {}).values()), None)
        unter = dict(kurs_cfg["unterwaehrungen"])
        kurs_werte, luecken = kurse(
            conn,
            isin,
            list(stichtage),
            umsatz.waehrung if umsatz else None,
            unter,
            int(kurs_cfg["max_abstand_tage"]),
        )
        werte.update(kurs_werte)
        parameter["unterwaehrungen"] = unter
    return Reihen(
        subjekt=issuer_id,
        stichtage=tuple(stichtage),
        werte=werte,
        splits=splits(
            conn,
            issuer_id,
            as_of,
            cmap["split_reihe"],
            Decimal(quality_cfg["split"]["toleranz"]),
        ),
        luecken=luecken,
        parameter=parameter,
    )


def reihen_aktuell(
    conn: duckdb.DuckDBPyConnection,
    basis: Reihen,
    isin: str | None,
    heute: date,
    kurs_cfg: dict[str, Any],
) -> Reihen | None:
    """Dieselben Reihen, aber mit dem letzten Schlusskurs bis `heute` am letzten Stichtag statt
    dem Kurs am Geschäftsjahresende. Für die aktuelle Bewertung (Statistik `aktuell`). None, wenn
    es keinen aktuellen Kurs gibt."""
    if isin is None or not basis.stichtage or "kurs" in basis.luecken:
        return None
    stichtag = basis.stichtage[0]
    k = store.price_on_or_before(conn, isin, heute)
    if k is None or dq.kurs_veraltet(k.date, heute, int(kurs_cfg["max_abstand_tage"])):
        return None
    neu: dict[str, dict[date, Eingabe]] = {"kurs": {stichtag: _kurs_eingabe(k, stichtag)}}
    unter = dict(kurs_cfg["unterwaehrungen"])
    umsatz = basis.werte.get("revenue", {}).get(stichtag)
    haupt = unter.get(str(k.currency), str(k.currency))
    for w in _fx_waehrungen(haupt, umsatz.waehrung if umsatz else None):
        f = store.fx_on_or_before(conn, str(w), k.date)
        if f is not None:
            neu[f"fx_{w}"] = {stichtag: _fx_eingabe(f, stichtag)}
    werte = {name: dict(je) for name, je in basis.werte.items()}
    for name, je in neu.items():
        werte.setdefault(name, {}).update(je)
    return replace(basis, werte=werte)
