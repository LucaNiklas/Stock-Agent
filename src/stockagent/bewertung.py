"""Einen Titel bewerten: Note, Konfidenz, Risiko, Kategorie (Bauschritt 5, SPEC 6, ADR 0005).

Ablauf je angefragter ISIN:

1. Eigene Daten sicherstellen: Abschlusswerte (SEC), Kurse, Zinsen, Damodaran, Wechselkurse,
   Kennzahlen.
2. Scorecard und Branche aus dem SIC-Code und den Kennzahlregeln (`config/scorecards.yaml`,
   `config/sectors.yaml`, Bauschritt 8). Holdings: Status N mit Grund (Summe der Teile).
3. Vergleichsgruppe: dieselbe Scorecard, Unterbranche und Region, sonst stufenweise breiter
   (Unterbranche global, Scorecard in der Region, Scorecard global), bis mindestens 15 Titel.
   Bei mehr als 50 die mit dem ähnlichsten Umsatz (Umsatz aller SEC-Melder aus der
   Frames-Schnittstelle, ohne Kurs). Daten der Gruppe werden geladen, wenn sie älter als eine
   Woche sind.
4. Note, Konfidenz, Risiko, Bewertungsbedingung und Kategorie über `core/note.py`.
5. Speichern in `grades` und als Tagesstand in `grade_snapshots` (Notenkontrolle SPEC 14.2).

Alle Netzabrufe laufen über `Lader`, damit Tests ohne Netz laufen.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import duckdb
import yaml

from stockagent import (
    esef_update,
    fx_update,
    insider_update,
    kapitalmarkt_update,
    metrics_update,
    prices_update,
    sec_update,
)
from stockagent.core import (
    dq,
    fx,
    gscore,
    insider,
    marktrisiko,
    momentum,
    note,
    sektoren,
    vergleichsgruppe,
)
from stockagent.core.calc import Rechenweg
from stockagent.data import concepts, inputs, quality, store
from stockagent.data.sources import sec
from stockagent.paths import Paths

Progress = Callable[[str], None]


def _noop(_: str) -> None:
    pass


@dataclass
class Lader:
    """Netzabrufe. In Tests durch Attrappen ersetzt."""

    sec: Callable[[Paths, list[str]], object] = lambda p, i: sec_update.update(p, isins=i)
    kurse: Callable[[Paths, list[str]], object] = lambda p, i: prices_update.update(p, i)
    markt: Callable[[Paths], object] = lambda p: (
        kapitalmarkt_update.zinsen_update(p),
        kapitalmarkt_update.damodaran_update(p),
    )
    wechselkurse: Callable[[Paths], object] = lambda p: fx_update.update(p)
    kennzahlen: Callable[[Paths, list[str]], object] = lambda p, i: metrics_update.update(
        p, isins=i
    )
    umsatz: Callable[[Paths, str, list[str]], None] = field(default=lambda p, z, k: None)
    esef: Callable[[Paths, list[str]], object] = lambda p, i: esef_update.update(p, i)
    insider: Callable[[Paths, list[str]], object] = lambda p, i: insider_update.update(p, i)


def umsatz_laden(paths: Paths, zeitraum: str, konzepte: list[str]) -> None:
    """Umsatz aller SEC-Melder für ein Kalenderjahr (je Konzept ein Abruf)."""
    cfg = yaml.safe_load((paths.config / "sources.yaml").read_text("utf-8"))
    client = sec.SecClient(cfg["sec"], sec.user_agent(paths.root), paths.raw)
    conn = store.connect(paths.db)
    try:
        for konzept in konzepte:
            try:
                zeilen, ref = client.frame(konzept, zeitraum)
            except Exception:
                continue
            store.save_revenue_frame(
                conn,
                zeitraum,
                konzept,
                [(z.cik, z.wert, z.start, z.ende, z.accession) for z in zeilen],
                ref.sha256,
                ref.retrieved_at,
            )
    finally:
        conn.close()


def standard_lader() -> Lader:
    return Lader(umsatz=umsatz_laden)


@dataclass
class Bewertung:
    isin: str
    note: str
    grund: str | None = None
    grade: store.GradeRow | None = None
    gruppe: list[str] = field(default_factory=list)
    stufe: str | None = None


@dataclass(frozen=True)
class Konfig:
    scoring: dict[str, Any]
    scorecards: dict[str, Any]
    sectors: dict[str, Any]
    metrics: dict[str, Any]
    cmap: dict[str, Any]
    horizonte: dict[str, Any] = field(default_factory=dict)
    insider: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def laden(cls, config: Any) -> Konfig:
        def yml(name: str) -> dict[str, Any]:
            data: dict[str, Any] = yaml.safe_load((config / name).read_text("utf-8"))
            return data

        return cls(
            yml("scoring.yaml"),
            yml("scorecards.yaml"),
            yml("sectors.yaml"),
            yml("metrics.yaml"),
            yml("concept_map.yaml"),
            yml("horizonte.yaml"),
            yml("insider_thresholds.yaml"),
        )


@dataclass(frozen=True)
class Titel:
    """Ein Kandidat: Emittent mit ISIN, SIC, Land und Umsatz."""

    isin: str
    issuer_id: str
    sic: int | None
    land: str | None


def _titel(conn: duckdb.DuckDBPyConnection) -> list[Titel]:
    """Alle Stammaktien mit SEC-Melder (keine Hinterlegungsscheine), je Emittent eine ISIN."""
    rows = conn.execute(
        "SELECT m.isin, m.cik, i.sector_sic, l.country FROM isin_cik m "
        "JOIN listings l ON l.isin = m.isin "
        "LEFT JOIN issuers i ON i.issuer_id = 'sec:' || m.cik "
        "WHERE m.cik IS NOT NULL AND m.status = 'zugeordnet' AND NOT l.is_receipt "
        "ORDER BY m.isin"
    ).fetchall()
    out: dict[str, Titel] = {}
    for isin, cik, sic, land in rows:
        iid = sec.issuer_id(cik)
        if iid not in out:
            out[iid] = Titel(isin, iid, int(sic) if sic and str(sic).isdigit() else None, land)
    return list(out.values())


def _veraltet(
    conn: duckdb.DuckDBPyConnection,
    issuer_id: str,
    jetzt: datetime,
    tage: int,
    version: str | None = None,
) -> bool:
    """Kennzahlen neu rechnen, wenn älter als `tage` oder mit einer anderen Methodik-Version
    gerechnet (sonst fehlen neue Kennzahlen, etwa die der Branchen-Scorecards)."""
    row = conn.execute(
        "SELECT computed_at, methodology_version FROM metric_runs WHERE issuer_id = ? "
        "ORDER BY computed_at DESC LIMIT 1",
        [issuer_id],
    ).fetchone()
    if row is None or row[0] is None:
        return True
    if version is not None and str(row[1]) != version:
        return True
    return not dq.juenger_als(row[0].date(), jetzt.date(), tage)


def _regel(cfg: Konfig, name: str) -> dict[str, Any]:
    return next(r for r in cfg.scorecards["zuordnung"] if r.get("regel") == name)


def _wachstum_ohne_gewinn(
    conn: duckdb.DuckDBPyConnection,
    issuer_id: str,
    werte: dict[tuple[str, str], Decimal | None],
    regel: dict[str, Any],
) -> bool:
    """EBIT-Marge in den letzten `jahre` Geschäftsjahren negativ und Umsatzwachstum (3 Jahre
    je Jahr) über der Schwelle (SPEC 3.11)."""
    jahre = int(regel["jahre"])
    margen = sorted(
        (r for r in store.load_metrics(conn, issuer_id, metric_id="ebit_margin", statistik="wert")),
        key=lambda r: r.period_end,
        reverse=True,
    )[:jahre]
    wachstum = werte.get(("revenue_cagr_3y", "wert"))
    return (
        len(margen) == jahre
        and all(r.value is not None and r.value < 0 for r in margen)
        and wachstum is not None
        and wachstum > Decimal(str(regel["umsatzwachstum"]))
    )


def _holding(werte: dict[tuple[str, str], Decimal | None], regel: dict[str, Any]) -> bool:
    anteil = werte.get(("holding_share", "wert"))
    return anteil is not None and anteil > Decimal(str(regel["schwelle"]))


def _kappungen(
    conn: duckdb.DuckDBPyConnection,
    issuer_id: str,
    werte: dict[tuple[str, str], Decimal | None],
    metrics_cfg: dict[str, Any],
    scoring: dict[str, Any],
    erlaubt: list[str] | None = None,
) -> tuple[list[str], bool]:
    """Kappungen nach SPEC 6.2 Nr. 6 und ob ein Stopp-Flag (3.9) vorliegt. `erlaubt`: die
    Kappungen, die für die Scorecard gelten (None = alle)."""
    alle, stopp = _alle_kappungen(conn, issuer_id, werte, metrics_cfg, scoring)
    if erlaubt is None:
        return alle, stopp
    return [k for k in alle if k in erlaubt], stopp and "stopp_flag" in erlaubt


def _alle_kappungen(
    conn: duckdb.DuckDBPyConnection,
    issuer_id: str,
    werte: dict[tuple[str, str], Decimal | None],
    metrics_cfg: dict[str, Any],
    scoring: dict[str, Any],
) -> tuple[list[str], bool]:
    schwellen = {d["id"]: d.get("schwellen", {}) for d in metrics_cfg["metrics"]}
    out: list[str] = []
    stopp = False
    zinsdeckung = werte.get(("interest_coverage", "wert"))
    if zinsdeckung is not None and zinsdeckung < 2:
        out.append("stopp_flag")
        stopp = True
    z = werte.get(("altman_z_double_prime", "wert"))
    if z is not None and z < Decimal(str(schwellen["altman_z_double_prime"]["gefahr_unter"])):
        out.append("altman_gefahr")
    m = werte.get(("beneish_m_score", "wert"))
    if m is not None and m > Decimal(str(schwellen["beneish_m_score"]["eskalation_ueber"])):
        out.append("beneish_ueber_schwelle")
    fcf = sorted(
        (r for r in store.load_metrics(conn, issuer_id, metric_id="fcf", statistik="wert")),
        key=lambda r: r.period_end,
        reverse=True,
    )[: int(scoring["fcf_negativ_jahre"])]
    nd = werte.get(("net_debt_to_ebitda", "wert"))
    if (
        len(fcf) == int(scoring["fcf_negativ_jahre"])
        and all(r.value is not None and r.value < 0 for r in fcf)
        and nd is not None
        and nd > int(scoring["verschuldung_ebitda_max"])
    ):
        out.append("fcf_negativ_und_verschuldet")
    return out, stopp


def _boersenwert_eur(
    conn: duckdb.DuckDBPyConnection,
    werte: dict[tuple[str, str], Decimal | None],
    waehrung: str | None,
) -> Decimal | None:
    mc = werte.get(("market_cap", "aktuell")) or werte.get(("market_cap", "wert"))
    if mc is None or waehrung is None:
        return None
    if waehrung == "EUR":
        return mc
    k = store.fx_on_or_before(conn, waehrung, datetime.now(UTC).date())
    return None if k is None else marktrisiko.in_eur(mc, k.per_eur, 1)


def _risikotage(
    conn: duckdb.DuckDBPyConnection,
    isin: str,
    unter: dict[str, str],
    reihen: dict[str, tuple[list[date], list[Decimal]]] | None = None,
) -> list[marktrisiko.Tag]:
    """Tageskurse in EUR. `reihen` hält die Referenzkurse je Währung über mehrere Aufrufe
    (Firma und Vergleichsgruppe), damit sie nur einmal gelesen werden."""
    reihen = {} if reihen is None else reihen
    tage = []
    for p in store.load_prices(conn, isin):
        if p.currency is None:
            continue
        haupt = fx.hauptwaehrung(p.currency, unter)
        teiler = fx.UNTERWAEHRUNG_TEILER if haupt != p.currency else 1
        je_eur = None
        if haupt != "EUR":
            if haupt not in reihen:
                s = store.fx_series(conn, haupt)
                reihen[haupt] = ([d for d, _ in s], [v for _, v in s])
            je_eur = fx.referenzkurs_am(*reihen[haupt], p.date)
            if je_eur is None:
                continue
        tage.append(marktrisiko.Tag(p.date, marktrisiko.in_eur(p.close, je_eur, teiler), p.volume))
    return tage


def _eigener_umsatz_usd(
    conn: duckdb.DuckDBPyConnection, issuer_id: str, cmap: dict[str, Any]
) -> Decimal:
    """Umsatz des letzten Geschäftsjahres in USD, wenn die Firma nicht in den Frames steht
    (IFRS-Berichte in anderer Währung, Bauschritt 7). Umrechnung im Rechenweg zum EZB-Kurs am
    Stichtag. 0, wenn er fehlt (dann gilt die Reihenfolge der Kennung)."""
    facts = store.pit_query(conn, as_of=datetime.now(UTC), issuer_id=issuer_id)
    stichtage = quality.jahresstichtage(facts, quality.kern_konzepte(cmap))
    if not stichtage:
        return Decimal(0)
    t = stichtage[0]
    treffer = [
        f
        for (start, ende), f in concepts.resolve(facts, cmap["us-gaap"]["revenue"]).items()
        if ende == t and start is not None
    ]
    if not treffer or treffer[0].currency is None:
        return Decimal(0)
    e = inputs.eingabe(treffer[0])
    if e.waehrung == "USD":
        return e.wert
    kurse = {}
    for w in {str(e.waehrung), "USD"}.difference({"EUR"}):
        k = store.fx_on_or_before(conn, w, t)
        if k is None:
            return Decimal(0)
        kurse[w] = inputs._fx_eingabe(k, t)
    r = Rechenweg("umsatz_usd", "1.0", issuer_id, t.isoformat(), pflicht=())
    return fx.umrechnen(r, "umsatz_in_usd", e, "USD", kurse, {}).wert


def _gruppe_waehlen(
    conn: duckdb.DuckDBPyConnection,
    eigen: Titel,
    alle: list[Titel],
    cfg: Konfig,
    umsatz: dict[str, Decimal],
    eigen_umsatz: Decimal | None,
) -> tuple[list[Titel], str]:
    vg = cfg.scoring["vergleichsgruppe"]
    mindest, hoechst = int(vg["mindest"]), int(vg["hoechst"])
    eb = sektoren.branche(eigen.sic, cfg.sectors)
    esc = sektoren.scorecard(eigen.sic, False, cfg.scorecards).id
    er = sektoren.region(eigen.land, vg["regionen"])

    def passt(t: Titel, branche: bool, region: bool) -> bool:
        if t.issuer_id == eigen.issuer_id or t.issuer_id.removeprefix("sec:") not in umsatz:
            return False
        if sektoren.scorecard(t.sic, False, cfg.scorecards).id != esc:
            return False
        if branche:
            tb = sektoren.branche(t.sic, cfg.sectors)
            if eb is None or tb is None or tb.unter != eb.unter:
                return False
        return not region or sektoren.region(t.land, vg["regionen"]) == er

    stufen = [
        ("Unterbranche in der Region", True, True),
        ("Unterbranche weltweit", True, False),
        ("Scorecard in der Region", False, True),
        ("Scorecard weltweit", False, False),
    ]
    kandidaten: list[Titel] = []
    stufe = stufen[-1][0]
    for name, b, r in stufen:
        kandidaten = [t for t in alle if passt(t, b, r)]
        stufe = name
        if len(kandidaten) >= mindest:
            break
    if eigen_umsatz is None:
        eigen_umsatz = umsatz.get(eigen.issuer_id.removeprefix("sec:")) or _eigener_umsatz_usd(
            conn, eigen.issuer_id, cfg.cmap
        )
    je = {t.issuer_id: t for t in kandidaten}
    ausgewaehlt = vergleichsgruppe.naechste(
        eigen_umsatz, {iid: umsatz[iid.removeprefix("sec:")] for iid in je}, hoechst
    )
    return [je[i] for i in ausgewaehlt], stufe


def bewerten(
    paths: Paths,
    isin: str,
    *,
    lader: Lader | None = None,
    now: datetime | None = None,
    progress: Progress = _noop,
    gruppe_laden: bool = True,
) -> Bewertung:
    now = now or datetime.now(UTC)
    lader = lader or standard_lader()
    cfg = Konfig.laden(paths.config)
    isin = isin.upper()
    vg = cfg.scoring["vergleichsgruppe"]
    tage = int(vg["erneuern_tage"])
    version = str(cfg.metrics["methodology_version"])

    # 1. Eigene Daten
    progress(f"{isin}: eigene Daten")
    lader.wechselkurse(paths)
    lader.markt(paths)
    conn = store.connect(paths.db)
    try:
        issuer = metrics_update.issuer_for_isin(conn, isin)
    finally:
        conn.close()
    if issuer is None:
        lader.sec(paths, [isin])
        conn = store.connect(paths.db)
        try:
            issuer = metrics_update.issuer_for_isin(conn, isin)
        finally:
            conn.close()
    if issuer is None:
        # Kein SEC-Melder: ESEF-Bericht über die LEI (Bauschritt 7)
        progress(f"{isin}: ESEF-Berichte über die LEI")
        lader.esef(paths, [isin])
        conn = store.connect(paths.db)
        try:
            issuer = metrics_update.issuer_for_isin(conn, isin)
        finally:
            conn.close()
        if issuer is not None:
            lader.kurse(paths, [isin])
            lader.kennzahlen(paths, [isin])
    if issuer is None:
        return _n(
            paths,
            isin,
            None,
            now,
            "weder SEC-Melder noch ESEF-Bericht bei filings.xbrl.org (deutsche Berichte fehlen "
            "dort, ADR 0009)",
        )
    conn = store.connect(paths.db)
    try:
        frisch = not _veraltet(conn, issuer, now, tage, version)
    finally:
        conn.close()
    if not frisch:
        lader.sec(paths, [isin])
        lader.kurse(paths, [isin])
        lader.kennzahlen(paths, [isin])
    if issuer.startswith("sec:"):
        # Insidergeschäfte nur für den angefragten Titel (Säule mit festem Wert, kein Rang)
        progress(f"{isin}: Insidergeschäfte (Form 4)")
        lader.insider(paths, [isin])

    conn = store.connect(paths.db)
    try:
        werte = store.metrics_map(conn, issuer)
        if not werte:
            return _n(paths, isin, issuer, now, "keine Kennzahlen (kein Jahresbericht)", conn)
        alle = _titel(conn)
        eigen = next((t for t in alle if t.issuer_id == issuer), None)
        if eigen is None:
            i = store.load_issuer(conn, issuer)
            sic = int(i.sector_sic) if i and i.sector_sic and i.sector_sic.isdigit() else None
            eigen = Titel(isin, issuer, sic, (store.listing_info(conn, isin) or ("", None))[1])
        sc = sektoren.scorecard(
            eigen.sic,
            _wachstum_ohne_gewinn(conn, issuer, werte, _regel(cfg, "wachstum_ohne_gewinn")),
            cfg.scorecards,
            holding=_holding(werte, _regel(cfg, "holding")),
        )
        sc_cfg = cfg.scorecards["scorecards"][sc.id]
        if "nicht_bewertbar" in sc_cfg:
            return _n(paths, isin, issuer, now, str(sc_cfg["nicht_bewertbar"]), conn)
    finally:
        conn.close()

    # 2. Vergleichsgruppe
    zeitraum = f"CY{now.year - 1}"
    konzepte = list(cfg.cmap["us-gaap"]["revenue"])
    conn = store.connect(paths.db)
    try:
        geladen = store.revenue_frame_loaded(conn, zeitraum)
    finally:
        conn.close()
    if geladen is None or not dq.juenger_als(geladen.date(), now.date(), 30):
        progress(f"Umsatz aller SEC-Melder {zeitraum}")
        lader.umsatz(paths, zeitraum, konzepte)
    conn = store.connect(paths.db)
    try:
        umsatz = store.revenues(conn, zeitraum, konzepte)
        gruppe, stufe = _gruppe_waehlen(conn, eigen, alle, cfg, umsatz, None)
        alt = [t for t in gruppe if _veraltet(conn, t.issuer_id, now, tage, version)]
    finally:
        conn.close()
    if gruppe_laden and alt:
        # Je Titel vollständig (Abschluss, Kurse, Kennzahlen), damit ein Abbruch das Geladene
        # behält und der Fortschritt sichtbar ist
        for nr, titel in enumerate(alt, start=1):
            progress(f"Vergleichsgruppe: Titel {nr} von {len(alt)} laden ({titel.isin})")
            lader.sec(paths, [titel.isin])
            lader.kurse(paths, [titel.isin])
            lader.kennzahlen(paths, [titel.isin])

    # 3. Note
    conn = store.connect(paths.db)
    try:
        return _note(conn, paths, cfg, isin, issuer, eigen, sc.id, gruppe, stufe, now)
    finally:
        conn.close()


def _n(
    paths: Paths,
    isin: str,
    issuer: str | None,
    now: datetime,
    grund: str,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> Bewertung:
    eigene = conn is None
    conn = conn or store.connect(paths.db)
    try:
        version = str(Konfig.laden(paths.config).metrics["methodology_version"])
        g = store.GradeRow(
            isin,
            issuer,
            now,
            None,
            None,
            None,
            None,
            "N",
            grund,
            None,
            None,
            "Nicht bewertbar",
            None,
            None,
            None,
            version,
            now,
        )
        store.save_grade(conn, g)
        store.save_snapshot(conn, now.date(), g, None, None)
    finally:
        if eigene:
            conn.close()
    return Bewertung(isin, "N", grund, g)


def _note(
    conn: duckdb.DuckDBPyConnection,
    paths: Paths,
    cfg: Konfig,
    isin: str,
    issuer: str,
    eigen: Titel,
    scorecard_id: str,
    gruppe: list[Titel],
    stufe: str,
    now: datetime,
) -> Bewertung:
    werte = store.metrics_map(conn, issuer)
    mit_werten = [(t, w) for t in gruppe if (w := store.metrics_map(conn, t.issuer_id))]
    gruppe_werte = [w for _, w in mit_werten]
    if len(gruppe_werte) < int(cfg.scoring["vergleichsgruppe"]["mindest"]) - 1:
        return _n(
            paths,
            isin,
            issuer,
            now,
            f"Vergleichsgruppe zu klein ({len(gruppe_werte)} Titel mit Kennzahlen)",
            conn,
        )
    sc_cfg = cfg.scorecards["scorecards"][scorecard_id]
    kappungen, stopp = _kappungen(
        conn, issuer, werte, cfg.metrics, cfg.scoring, sc_cfg.get("kappungen")
    )
    # Eigene Säulengewichte der Scorecard (SPEC 3.11), sonst die aus config/scoring.yaml
    scoring = {
        **cfg.scoring,
        "saeulen_gewichte": sc_cfg.get("saeulen_gewichte", cfg.scoring["saeulen_gewichte"]),
    }
    # Insider-Signal der Firma (SPEC 3.8): fester Wert der Säule, kein Rang in der Gruppe
    isig = insider.signal(issuer, store.load_insider(conn, issuer, now), now.date(), cfg.insider)
    werte = {**werte, insider.KENNZAHL: isig.saeule}
    gscore_weg: dict[str, object] | None = None
    if any(k["kennzahl"] == gscore.KENNZAHL[0] for s in sc_cfg["saeulen"].values() for k in s):
        werte, gruppe_werte, gscore_weg = gscore.ergaenzen(
            issuer, now.date().isoformat(), werte, gruppe_werte
        )

    # Kursmomentum der Firma und der Gruppe (ADR 0011), als Statistik `aktuell`
    unter = yaml.safe_load((paths.config / "sources.yaml").read_text("utf-8"))["ecb"][
        "unterwaehrungen"
    ]
    mcfg = cfg.horizonte["momentum"]
    fx_reihen: dict[str, tuple[list[date], list[Decimal]]] = {}
    tage = _risikotage(conn, isin, unter, fx_reihen)

    def mit_momentum(
        isin_: str, w: dict[tuple[str, str], Decimal | None], reihe: list[marktrisiko.Tag]
    ) -> tuple[dict[tuple[str, str], Decimal | None], dict[str, object]]:
        m, weg = momentum.momentum(
            isin_,
            reihe,
            now.date(),
            int(mcfg["max_abstand_tage"]),
            store.last_report_date(conn, issuer_von.get(isin_, ""), now),
            int(mcfg["bericht_max_tage"]),
        )
        return {**w, **{(k, "aktuell"): v for k, v in m.items()}}, weg

    issuer_von = {isin: issuer, **{t.isin: t.issuer_id for t, _ in mit_werten}}
    werte, momentum_weg = mit_momentum(isin, werte, tage)
    gruppe_werte = [
        mit_momentum(t.isin, w, _risikotage(conn, t.isin, unter, fx_reihen))[0]
        for (t, _), w in zip(mit_werten, gruppe_werte, strict=True)
    ]

    # Note je Anlagehorizont: gleiche Säulen, nur das Gewicht von Momentum ändert sich
    sc_mit = {**sc_cfg, "saeulen": {**sc_cfg["saeulen"], "momentum": mcfg["kennzahlen"]}}
    je_horizont: dict[str, note.NotenErgebnis] = {}
    for h, hcfg in cfg.horizonte["horizonte"].items():
        gewichte = note.gewichte_horizont(
            scoring["saeulen_gewichte"], Decimal(str(hcfg["momentum_anteil"]))
        )
        je_horizont[h] = note.note(
            issuer,
            now.date().isoformat(),
            werte,
            gruppe_werte,
            sc_mit,
            {**scoring, "saeulen_gewichte": gewichte},
            kappungen,
        )
    standard = str(cfg.horizonte["standard"])
    erg = je_horizont[standard]
    if erg.note == "N":
        return _n(paths, isin, issuer, now, erg.grund or "Note nicht berechenbar", conn)

    # Konfidenz. Historie = Geschäftsjahre mit Jahreswerten in den Kennzahlen der Scorecard
    # (vorher Bruttomarge und FCF, die es bei Banken und Versicherern nicht gibt: dort immer K4)
    eigene_kz = {
        str(k["kennzahl"])
        for s in sc_cfg["saeulen"].values()
        for k in s
        if k["statistik"] == "wert" and k["kennzahl"] != gscore.KENNZAHL[0]
    }
    jahre = len(
        {
            r.period_end
            for kz in sorted(eigene_kz)
            for r in store.load_metrics(conn, issuer, metric_id=kz, statistik="wert")
            if r.value is not None
        }
    )
    flags = store.load_dq_flags(conn, issuer)
    quellen_ok = not any(f.severity == "stopp" for f in flags)
    waehrung = store.report_currency(conn, issuer) or "USD"
    mc_eur = _boersenwert_eur(conn, werte, waehrung)
    groesse = note.groessenklasse(mc_eur, cfg.scoring["groessenklassen"])
    konf, konf_gruende = note.konfidenz(
        jahre, erg.abdeckung, groesse, quellen_ok, True, cfg.scoring["konfidenz"]
    )
    konf, konf_abschlag = note.konfidenz_abschlag(
        konf,
        int(sc_cfg.get("konfidenz_abschlag", 0)),
        f"Scorecard {sc_cfg['name']} mit Hilfsmaß ohne eigene Prüfung (SPEC 3.11)",
    )
    if konf_abschlag:
        konf_gruende.append(konf_abschlag)

    # Risiko
    risiko_eingaben: dict[str, Decimal | str | None] = {
        "volatilitaet_3j": marktrisiko.volatilitaet(tage),
        "drawdown_5j": marktrisiko.drawdown(tage),
        "verschuldung_ebitda": (
            werte.get((str(sc_cfg["risiko_verschuldung"]), "wert"))
            if sc_cfg.get("risiko_verschuldung")
            else None
        )
        if "risiko_verschuldung" in sc_cfg
        else werte.get(("net_debt_to_ebitda", "wert")),
        "amihud": marktrisiko.amihud(tage),
        "ebit_marge_streuung": werte.get(
            (str(sc_cfg.get("risiko_ergebnis_streuung", "ebit_margin")), "stdabw")
        ),
        "groesse": groesse,
    }
    risiko, risiko_stufen = note.risiko(risiko_eingaben, cfg.scoring["risiko"])

    # Bewertungsbedingung (SPEC 3.6)
    r = Rechenweg("bewertungsbedingung", note.VERSION, issuer, now.date().isoformat(), pflicht=())
    mult_cfg = sc_cfg.get("multiples") or [
        {"kennzahl": "ev_ebit", "richtung": "niedrig"},
        {"kennzahl": "pe", "richtung": "niedrig"},
        {"kennzahl": "fcf_yield", "richtung": "hoch"},
    ]
    multiples = {str(k["kennzahl"]): werte.get((str(k["kennzahl"]), "aktuell")) for k in mult_cfg}
    gruppe_mult = [{k: w.get((k, "aktuell")) for k in multiples} for w in gruppe_werte]
    hoch = {str(k["kennzahl"]) for k in mult_cfg if k["richtung"] == "hoch"}
    abschlag = vergleichsgruppe.multiples_abschlag(r, multiples, gruppe_mult, hoch)
    luecke = werte.get(("growth_gap", "aktuell")) if sc_cfg.get("reverse_dcf", True) else None
    bull = werte.get(("dcf_bull", "aktuell"))
    preis = store.price_on_or_before(conn, isin, now.date())
    min_abschlag = Decimal(str(cfg.scoring["bewertungsbedingung"]["min_discount_to_multiples"]))
    bedingung: bool | None = None
    if luecke is not None or abschlag is not None:
        bedingung = (luecke is not None and luecke < 0) or (
            abschlag is not None and abschlag >= min_abschlag
        )
    kurs_ueber_bull = (
        bull is not None
        and werte.get(("margin_of_safety", "aktuell")) is not None
        and werte.get(("dcf_base", "aktuell")) is not None
        and _kurs_ueber_bull(werte)
    )
    if kurs_ueber_bull:
        bedingung = False

    # Kategorie mit Hysterese, je Horizont
    vor = conn.execute(
        "SELECT score, horizonte_json FROM grade_snapshots WHERE isin = ? AND snapshot_date < ? "
        "ORDER BY snapshot_date DESC LIMIT 1",
        [isin, now.date()],
    ).fetchone()
    vor_h = json.loads(vor[1]) if vor and vor[1] else {}
    horizonte: dict[str, dict[str, Any]] = {}
    for h, e in je_horizont.items():
        hcfg = cfg.horizonte["horizonte"][h]
        if h == standard:
            vorher = [g for d, g in store.snapshot_grades(conn, isin) if d < now.date()]
            vor_score = vor[0] if vor else None
        else:
            vorher = [g for d, g in store.snapshot_grades_horizont(conn, isin, h) if d < now.date()]
            vor_score = (vor_h.get(h) or {}).get("score")
        aufwaerts = bool(vor_score and e.gesamt is not None and e.gesamt > Decimal(vor_score))
        k, k_grund = note.kategorie(
            e.note,
            konf,
            stopp,
            bedingung,
            vorher,
            aufwaerts,
            int(cfg.scoring["kategorie"]["hysterese_laeufe"]),
        )
        mindest = hcfg.get("kategorie_momentum_mindest")
        mom = e.saeulen.get("momentum")
        if k == "Attraktiv" and mindest is not None and (mom is None or mom < Decimal(mindest)):
            k = "Beobachten"
            k_grund = (
                f"{k_grund}, aber Kurstrend schwach (Momentum "
                f"{'unbekannt' if mom is None else f'{mom:.0f}'} unter {mindest}) für den Horizont "
                f"{hcfg['name']}"
            )
        horizonte[h] = {
            "name": hcfg["name"],
            "note": e.note,
            "score": str(e.gesamt) if e.gesamt is not None else None,
            "kategorie": k,
            "kategorie_grund": k_grund,
            "momentum_anteil": str(hcfg["momentum_anteil"]),
            "saeulen": {s: (str(v) if v is not None else None) for s, v in e.saeulen.items()},
        }
    kat, kat_grund = horizonte[standard]["kategorie"], horizonte[standard]["kategorie_grund"]

    branche = sektoren.branche(eigen.sic, cfg.sectors)
    detail = {
        "saeulen": {k: (str(v) if v is not None else None) for k, v in erg.saeulen.items()},
        "abdeckung": str(erg.abdeckung),
        "kappungen": erg.kappungen,
        "raenge": [
            {
                **asdict(x),
                "wert": str(x.wert) if x.wert is not None else None,
                "perzentil": str(x.perzentil) if x.perzentil is not None else None,
            }
            for x in erg.raenge
        ],
        "gruppe": [t.isin for t in gruppe],
        "gruppe_stufe": stufe,
        "konfidenz_gruende": konf_gruende,
        "risiko_stufen": risiko_stufen,
        "risiko_eingaben": {
            k: (str(v) if v is not None else None) for k, v in risiko_eingaben.items()
        },
        "bewertungsbedingung": {
            "erfuellt": bedingung,
            "growth_gap": str(luecke) if luecke is not None else None,
            "multiples_abschlag": str(abschlag) if abschlag is not None else None,
            "kurs_ueber_bull": kurs_ueber_bull,
            "rechenweg": [asdict(s) for s in r.schritte],
        },
        "kategorie_grund": kat_grund,
        "rechenweg_note": erg.rechenweg,
        "boersenwert_eur": str(mc_eur) if mc_eur is not None else None,
        "scorecard": sc_cfg["name"],
        "g_score": gscore_weg,
        "insider": {
            "saeule": str(isig.saeule) if isig.saeule is not None else None,
            "summe": str(isig.summe) if isig.summe is not None else None,
            "grund": isig.grund,
            "geschaefte": [
                {**asdict(g), "handelstag": g.handelstag.isoformat(), "beitrag": str(g.beitrag)}
                for g in isig.geschaefte
            ],
            "rechenweg": isig.rechenweg,
        },
        "horizont_standard": standard,
        "horizonte": horizonte,
        "momentum": momentum_weg,
    }
    g = store.GradeRow(
        isin,
        issuer,
        now,
        scorecard_id,
        f"{branche.haupt_name} / {branche.unter_name}" if branche else None,
        sektoren.region(eigen.land, cfg.scoring["vergleichsgruppe"]["regionen"]),
        erg.gesamt,
        erg.note,
        None,
        konf,
        risiko,
        kat,
        groesse,
        stufe,
        json.dumps(detail, ensure_ascii=False, default=str),
        str(cfg.metrics["methodology_version"]),
        now,
    )
    store.save_grade(conn, g)
    store.save_snapshot(
        conn,
        now.date(),
        g,
        preis.close if preis else None,
        preis.currency if preis else None,
        {h: {k: v[k] for k in ("note", "score", "kategorie")} for h, v in horizonte.items()},
    )
    return Bewertung(isin, erg.note, None, g, [t.isin for t in gruppe], stufe)


def _kurs_ueber_bull(werte: dict[tuple[str, str], Decimal | None]) -> bool:
    """Kurs über dem Bull-Szenario: Sicherheitsmarge des Base-Szenarios sagt base/kurs - 1,
    daraus kurs = base / (1 + marge). Vergleich ohne Rechnung über das Verhältnis bull/base."""
    r = Rechenweg("kurs_bull", note.VERSION, "", "", pflicht=())
    marge = werte[("margin_of_safety", "aktuell")]
    base, bull = werte[("dcf_base", "aktuell")], werte[("dcf_bull", "aktuell")]
    assert marge is not None and base is not None and bull is not None
    kurs = r.schritt("kurs", "base / (1 + marge)", base=base, marge=marge)
    return kurs > bull


def vergleichsgruppe_fuer(paths: Paths, isin: str) -> list[str]:
    conn = store.connect(paths.db)
    try:
        g = store.load_grade(conn, isin.upper())
    finally:
        conn.close()
    if g is None or g.detail_json is None:
        return []
    return list(json.loads(g.detail_json).get("gruppe", []))
