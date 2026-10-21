"""Kennzahlen rechnen und speichern (Bauschritt 3, Abteilung Berechnung, SPEC 8.1).

Ablauf je Firma:

1. Jahresreihen der Eingangswerte zum Datenstand `as_of` (`data/inputs.py`, HR-07).
2. Jede Kennzahl aus `config/metrics.yaml` für bis zu 10 Geschäftsjahre über den Rechenweg.
3. Trends je Kennzahl zum letzten Geschäftsjahr (`core/trends.py`), darin CP-05.
4. Hinweise an die Agenten aus `config/hinweise.yaml` (`core/hinweise.py`).
5. Speichern: `metrics` mit Rechenweg, `hinweise`, `metric_runs`.

Kein Sprachmodell, kein Netz. Gespeichert wird je Firma nur der letzte Lauf: Werte aller
Geschäftsjahre (für Trends und Verläufe) und die Trends, der vollständige Rechenweg aber nur
für die Jahreswerte des letzten Geschäftsjahres. Rechenwege von Vorjahren und Trends rechnen
`nachrechnen` und `nachrechnen_trend` bei Bedarf gleich nach. Die vertikale Analyse wird
nicht gespeichert, sondern bei der Anzeige gerechnet
(`core/trends.vertikal`).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import yaml

from stockagent.core import hinweise, registry, szenarien, trends, ttm
from stockagent.core.calc import Ergebnis as CalcErgebnis
from stockagent.core.calc import Rechenweg, rechne
from stockagent.core.hinweise import Hinweis, Kennzahlwert
from stockagent.core.reihen import Reihen
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
    sources: dict[str, Any]
    kapitalkosten: dict[str, Any] = field(default_factory=dict)
    # Lucas Festlegungen der Damodaran-Branche je ISIN (state/damodaran_branchen.yaml)
    branchen: dict[str, str] = field(default_factory=dict)
    # Lucas Festlegungen Aktien je Hinterlegungsschein (state/adr_verhaeltnis.yaml)
    adr: dict[str, str] = field(default_factory=dict)

    def kk_cfg(self) -> dict[str, Any] | None:
        if not self.kapitalkosten:
            return None
        return {
            **self.kapitalkosten,
            "boersen": self.sources.get("damodaran", {}).get("boersen", {}),
            "festgelegt": self.branchen,
        }

    def kurs_cfg(self) -> dict[str, Any]:
        return {
            **self.metrics["kurse"],
            "unterwaehrungen": self.sources["ecb"]["unterwaehrungen"],
            "adr": self.adr,
        }

    @classmethod
    def laden(cls, config: Path) -> Konfiguration:
        def yml(name: str) -> dict[str, Any]:
            data: dict[str, Any] = yaml.safe_load((config / name).read_text("utf-8"))
            return data

        def state(name: str) -> dict[str, str]:
            datei = config.parent / "state" / name
            if not datei.exists():
                return {}
            data = yaml.safe_load(datei.read_text("utf-8")) or {}
            return {str(k): str(v) for k, v in data.items()}

        branchen = state("damodaran_branchen.yaml")
        return cls(
            concepts.load(config),
            yml("quality.yaml"),
            yml("metrics.yaml"),
            yml("hinweise.yaml"),
            yml("sources.yaml"),
            yml("kapitalkosten.yaml") if (config / "kapitalkosten.yaml").exists() else {},
            branchen,
            state("adr_verhaeltnis.yaml"),
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


def isin_for_issuer(conn: duckdb.DuckDBPyConnection, issuer_id: str) -> str | None:
    """ISIN zum Emittenten, bevorzugt eine mit zugeordnetem Kurssymbol, Stammaktie vor
    Hinterlegungsschein."""
    isins = store.isins_for_issuer(conn, issuer_id)
    mit_kurs = [i for i in isins if (s := store.load_price_symbol(conn, i)) and s.symbol]
    return next(iter(mit_kurs or isins), None)


def _reihen(
    conn: duckdb.DuckDBPyConnection,
    issuer_id: str,
    as_of: datetime,
    cfg: Konfiguration,
    isin: str | None,
) -> Reihen:
    return inputs.reihen(
        conn,
        issuer_id,
        as_of,
        cfg.cmap,
        cfg.quality,
        isin=isin if isin is not None else isin_for_issuer(conn, issuer_id),
        kurs_cfg=cfg.kurs_cfg(),
        kk_cfg=cfg.kk_cfg(),
    )


def berechne(
    conn: duckdb.DuckDBPyConnection,
    issuer_id: str,
    as_of: datetime,
    cfg: Konfiguration,
    isin: str | None = None,
) -> Rechnung:
    """Alle Kennzahlen und Trends einer Firma zum Datenstand `as_of`, ohne zu speichern."""
    isin = isin if isin is not None else isin_for_issuer(conn, issuer_id)
    reihen = _reihen(conn, issuer_id, as_of, cfg, isin)
    if not reihen.stichtage:
        return Rechnung(issuer_id, None, fehler="Kein Jahresbericht mit Abschlusswerten")
    stichtag = reihen.stichtage[0]
    tcfg = cfg.metrics["trends"]
    waehrung = _waehrung(reihen)
    aktuell = inputs.reihen_aktuell(conn, reihen, isin, as_of.date(), cfg.kurs_cfg())
    ttm_stand = _ttm_reihen(conn, issuer_id, as_of, cfg, reihen, isin)
    werte: list[Kennzahlwert] = []
    for d in cfg.metrics["metrics"]:
        jahre = trends.jahresreihe(d, reihen, int(tcfg["max_jahre"]))
        version = str(d["version"])
        werte += [Kennzahlwert(d["id"], version, "wert", t, e) for t, e in jahre.items()]
        geld = waehrung if d["einheit"] == "monetary" else None
        tr = trends.trend(d, issuer_id, jahre, stichtag, geld, tcfg, cfg.quality["ausreisser"])
        werte += [Kennzahlwert(d["id"], version, s, stichtag, e) for s, e in tr.items()]
        if d.get("ttm") and ttm_stand is not None:
            # Letzte 12 Monate bis zum letzten Quartal, mit dem letzten Schlusskurs
            e = registry.berechne(d, ttm_stand, ttm_stand.stichtage[0])
            werte.append(Kennzahlwert(d["id"], version, "ttm", stichtag, e))
        if not d.get("kurs"):
            continue
        # Bewertung mit dem letzten Schlusskurs statt dem Kurs am Geschäftsjahresende
        jetzt = registry.berechne(d, aktuell, stichtag) if aktuell else None
        if jetzt is not None:
            werte.append(Kennzahlwert(d["id"], version, "aktuell", stichtag, jetzt))
        if d.get("historie_perzentil") and stichtag in jahre:
            p = trends.perzentil_historie(
                d, issuer_id, jahre, jetzt or jahre[stichtag], stichtag, tcfg
            )
            werte.append(Kennzahlwert(d["id"], version, "perzentil_historie", stichtag, p))
    flags = store.load_dq_flags(conn, issuer_id)
    h = hinweise.ableiten(werte, flags, stichtag, cfg.hinweise, cfg.metrics)
    return Rechnung(issuer_id, stichtag, werte, h)


def _ttm_reihen(
    conn: duckdb.DuckDBPyConnection,
    issuer_id: str,
    as_of: datetime,
    cfg: Konfiguration,
    reihen: Reihen,
    isin: str | None,
) -> Reihen | None:
    """Reihen mit dem TTM-Stichtag (letztes Quartal) vorne und dem letzten Schlusskurs."""
    teile = inputs.ttm(conn, issuer_id, as_of, cfg.cmap, reihen)
    if teile is None:
        return None
    quartal, stroeme, staende = teile
    stand = ttm.ttm_reihen(reihen, quartal, ttm.ttm_werte(issuer_id, quartal, stroeme, staende))
    return inputs.reihen_aktuell(conn, stand, isin, as_of.date(), cfg.kurs_cfg())


def nachrechnen(
    conn: duckdb.DuckDBPyConnection,
    issuer_id: str,
    as_of: datetime,
    metric_id: str,
    jahr: int,
    cfg: Konfiguration,
) -> CalcErgebnis | None:
    """Rechenweg einer Kennzahl für ein Vorjahr zum selben Datenstand wie der gespeicherte Lauf.

    Vorjahre speichern nur den Wert. Weil `pit_query` zum selben `as_of` dieselben Daten liefert,
    ergibt das Nachrechnen denselben Wert mit vollständigem Rechenweg (SPEC 12.5). None, wenn es
    das Geschäftsjahr im Datenstand nicht gibt."""
    reihen = _reihen(conn, issuer_id, as_of, cfg, None)
    treffer = [t for t in reihen.stichtage if t.year == jahr]
    definition = next(d for d in cfg.metrics["metrics"] if d["id"] == metric_id)
    return registry.berechne(definition, reihen, treffer[0]) if treffer else None


def nachrechnen_trend(
    conn: duckdb.DuckDBPyConnection,
    issuer_id: str,
    as_of: datetime,
    metric_id: str,
    statistik: str,
    cfg: Konfiguration,
) -> CalcErgebnis | None:
    """Rechenweg einer Trendstatistik zum selben Datenstand wie der gespeicherte Lauf."""
    reihen = _reihen(conn, issuer_id, as_of, cfg, None)
    if not reihen.stichtage:
        return None
    tcfg = cfg.metrics["trends"]
    d = next(m for m in cfg.metrics["metrics"] if m["id"] == metric_id)
    jahre = trends.jahresreihe(d, reihen, int(tcfg["max_jahre"]))
    geld = _waehrung(reihen) if d["einheit"] == "monetary" else None
    tr = trends.trend(
        d, issuer_id, jahre, reihen.stichtage[0], geld, tcfg, cfg.quality["ausreisser"]
    )
    return tr.get(statistik)


def dcf_mit_stufen(
    conn: duckdb.DuckDBPyConnection,
    issuer_id: str,
    as_of: datetime,
    wahl: dict[str, dict[str, str]],
    cfg: Konfiguration,
) -> dict[str, CalcErgebnis]:
    """DCF-Szenarien mit gewählten Stufen (Bewertungsagent A5, Bauschritt 6) mit dem letzten
    Schlusskurs. Rechnung und Prüfpunkte wie `dcf_bear` bis `dcf_bull`."""
    isin = isin_for_issuer(conn, issuer_id)
    reihen = _reihen(conn, issuer_id, as_of, cfg, isin)
    if not reihen.stichtage:
        return {}
    stichtag = reihen.stichtage[0]
    aktuell = inputs.reihen_aktuell(conn, reihen, isin, as_of.date(), cfg.kurs_cfg()) or reihen
    d = next(m for m in cfg.metrics["metrics"] if m["id"] == "dcf_base")
    out = {}
    for szenario, stufen in wahl.items():
        r = Rechenweg(
            f"dcf_{szenario}_a5",
            str(d["version"]),
            issuer_id,
            stichtag.isoformat(),
            pflicht=tuple(d["pruefpunkte"]),
        )

        def rechnung(r: Rechenweg, s: str = szenario, w: dict[str, str] = stufen) -> Decimal:
            return szenarien.szenario_mit_stufen(r, aktuell, stichtag, s, w)

        out[szenario] = rechne(r, rechnung)
    return out


def _waehrung(reihen: Reihen) -> str | None:
    return next((w.waehrung for w in reihen.werte.get("revenue", {}).values() if w.waehrung), None)


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
    return store.issuer_for_isin(conn, isin)


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
            r = berechne(conn, issuer, as_of, cfg, isin)
            if r.fehler:
                out.append(Ergebnis(isin, r, r.fehler))
                continue
            speichere(conn, r, as_of, cfg, now)
            out.append(Ergebnis(isin, r))
    finally:
        conn.close()
    return out
