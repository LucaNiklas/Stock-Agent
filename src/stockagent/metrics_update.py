"""Kennzahlen rechnen und speichern (Bauschritt 3, Abteilung Berechnung, SPEC 8.1).

Ablauf je Firma:

1. Jahresreihen der Eingangswerte zum Datenstand `as_of` (`data/inputs.py`, HR-07).
2. Jede Kennzahl aus `config/metrics.yaml` für bis zu 10 Geschäftsjahre über den Rechenweg.
3. Trends je Kennzahl zum letzten Geschäftsjahr (`core/trends.py`), darin CP-05.
4. Hinweise an die Agenten aus `config/hinweise.yaml` (`core/hinweise.py`).
5. Speichern: `metrics` mit Rechenweg, `hinweise`, `metric_runs`.

Kein Sprachmodell, kein Netz. Die vertikale Analyse wird nicht gespeichert, sondern bei der
Anzeige gerechnet (`core/trends.vertikal`).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import yaml

from stockagent.core import hinweise, trends
from stockagent.core.hinweise import Hinweis, Kennzahlwert
from stockagent.data import concepts, inputs, store
from stockagent.data.sources import sec
from stockagent.paths import Paths

Progress = Callable[[str], None]


def _noop(_: str) -> None:
    pass


@dataclass(frozen=True)
class Konfiguration:
    cmap: dict[str, Any]
    quality: dict[str, Any]
    metrics: dict[str, Any]
    hinweise: dict[str, Any]

    @classmethod
    def laden(cls, config: Path) -> Konfiguration:
        def yml(name: str) -> dict[str, Any]:
            data: dict[str, Any] = yaml.safe_load((config / name).read_text("utf-8"))
            return data

        return cls(
            concepts.load(config), yml("quality.yaml"), yml("metrics.yaml"), yml("hinweise.yaml")
        )


@dataclass
class Rechnung:
    issuer_id: str
    stichtag: date | None
    werte: list[Kennzahlwert] = field(default_factory=list)
    hinweise: list[Hinweis] = field(default_factory=list)
    fehler: str | None = None

    def zaehlung(self) -> Counter[str]:
        """Jahreswerte im Stichtagsjahr: berechnet, unknown (fehlende Eingabe), gestoppt."""
        c: Counter[str] = Counter()
        for w in self.werte:
            if w.statistik != "wert" or w.period_end != self.stichtag:
                continue
            e = w.ergebnis
            c[
                "berechnet" if e.wert is not None else "gestoppt" if e.ungereimtheit else "fehlt"
            ] += 1
        return c


def berechne(
    conn: duckdb.DuckDBPyConnection, issuer_id: str, as_of: datetime, cfg: Konfiguration
) -> Rechnung:
    """Alle Kennzahlen und Trends einer Firma zum Datenstand `as_of`, ohne zu speichern."""
    reihen = inputs.reihen(conn, issuer_id, as_of, cfg.cmap, cfg.quality)
    if not reihen.stichtage:
        return Rechnung(issuer_id, None, fehler="Kein Jahresbericht mit Abschlusswerten")
    stichtag = reihen.stichtage[0]
    tcfg = cfg.metrics["trends"]
    waehrung = next(
        (w.waehrung for w in reihen.werte.get("revenue", {}).values() if w.waehrung), None
    )
    werte: list[Kennzahlwert] = []
    for d in cfg.metrics["metrics"]:
        jahre = trends.jahresreihe(d, reihen, int(tcfg["max_jahre"]))
        version = str(d["version"])
        werte += [Kennzahlwert(d["id"], version, "wert", t, e) for t, e in jahre.items()]
        geld = waehrung if d["einheit"] == "monetary" else None
        tr = trends.trend(d, issuer_id, jahre, stichtag, geld, tcfg, cfg.quality["ausreisser"])
        werte += [Kennzahlwert(d["id"], version, s, stichtag, e) for s, e in tr.items()]
    flags = store.load_dq_flags(conn, issuer_id)
    h = hinweise.ableiten(werte, flags, stichtag, cfg.hinweise, cfg.metrics)
    return Rechnung(issuer_id, stichtag, werte, h)


def speichere(
    conn: duckdb.DuckDBPyConnection,
    rechnung: Rechnung,
    as_of: datetime,
    cfg: Konfiguration,
    now: datetime,
) -> str:
    return store.replace_metrics(
        conn,
        issuer_id=rechnung.issuer_id,
        as_of=as_of,
        stichtag=rechnung.stichtag,
        methodology_version=str(cfg.metrics["methodology_version"]),
        werte=rechnung.werte,
        hinweise=rechnung.hinweise,
        now=now,
    )


def issuer_for_isin(conn: duckdb.DuckDBPyConnection, isin: str) -> str | None:
    mapping = store.load_isin_cik(conn).get(isin.upper())
    return sec.issuer_id(mapping.cik) if mapping and mapping.cik else None


@dataclass
class Ergebnis:
    isin: str
    rechnung: Rechnung | None
    fehler: str | None = None


def update(
    paths: Paths,
    *,
    isins: list[str] | None = None,
    as_of: datetime | None = None,
    now: datetime | None = None,
    progress: Progress = _noop,
) -> list[Ergebnis]:
    """Kennzahlen für die ISINs rechnen und speichern. Ohne ISINs für alle Firmen mit Werten."""
    now = now or datetime.now(UTC)
    as_of = as_of or now
    cfg = Konfiguration.laden(paths.config)
    conn = store.connect(paths.db)
    out: list[Ergebnis] = []
    try:
        if isins:
            ziele = [(i.upper(), issuer_for_isin(conn, i)) for i in isins]
        else:
            mit_werten = store.issuer_ids_with_facts(conn)
            ziele = sorted(
                (isin, sec.issuer_id(m.cik))
                for isin, m in store.load_isin_cik(conn).items()
                if m.cik and sec.issuer_id(m.cik) in mit_werten
            )
        for isin, issuer in ziele:
            if issuer is None:
                out.append(Ergebnis(isin, None, "keinem SEC-Melder zugeordnet"))
                continue
            progress(f"Kennzahlen: {isin} ({issuer})")
            r = berechne(conn, issuer, as_of, cfg)
            if r.fehler:
                out.append(Ergebnis(isin, r, r.fehler))
                continue
            speichere(conn, r, as_of, cfg, now)
            out.append(Ergebnis(isin, r))
    finally:
        conn.close()
    return out
