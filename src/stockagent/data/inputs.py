"""Eingangswerte der Kennzahlen aus der Datenbank (Abteilung Berechnung, SPEC 8.1).

Liest über `pit_query` zum Zeitpunkt `as_of` (HR-07), ordnet Konzepte je Periode zu
(`config/concept_map.yaml`) und baut daraus `core.reihen.Reihen`: je interner Größe die Werte
an den Geschäftsjahresenden (Stände) oder über das Geschäftsjahr (Ströme). Dazu die
Split-Ereignisse aus den Deckblatt-Meldungen (DQ-08). Reine Auswahl, keine Arithmetik.
"""

from __future__ import annotations

from datetime import datetime
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


def reihen(
    conn: duckdb.DuckDBPyConnection,
    issuer_id: str,
    as_of: datetime,
    cmap: dict[str, Any],
    quality_cfg: dict[str, Any],
    max_jahre: int = 11,
) -> Reihen:
    """Jahresreihen aller internen Größen aus `cmap['us-gaap']` für bis zu `max_jahre` Jahre."""
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
    )
