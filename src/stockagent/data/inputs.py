"""Eingangswerte der Kennzahlen aus der Datenbank (Abteilung Berechnung, SPEC 8.1).

Liest über `pit_query` zum Zeitpunkt `as_of` (HR-07), ordnet Konzepte je Periode zu
(`config/concept_map.yaml`) und baut daraus `core.reihen.Reihen`: je interner Größe die Werte
an den Geschäftsjahresenden (Stände) oder über das Geschäftsjahr (Ströme). Dazu die
Split-Ereignisse aus den Deckblatt-Meldungen (DQ-08). Reine Auswahl, keine Arithmetik.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from itertools import pairwise
from typing import Any

import duckdb

from stockagent.core import abgeleitet, dq, identifiers
from stockagent.core.calc import Eingabe
from stockagent.core.reihen import Reihen, Split
from stockagent.core.ttm import Strom
from stockagent.data import concepts, quality, store
from stockagent.data.quality import ANNUAL_FORMS


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


def dividenden_yahoo(
    conn: duckdb.DuckDBPyConnection, isin: str, stichtage: list[date]
) -> dict[date, Eingabe]:
    """Anzahl der Dividendenereignisse bei Yahoo je Geschäftsjahr (nach dem Vorjahresstichtag
    bis zum Stichtag), nur für Jahre, die die gespeicherten Kurse ganz abdecken. Gegenprobe für
    Firmen ohne gemeldete Dividendenzahlung (METHODOLOGY_CHANGELOG 4.7). Reine Auswahl."""
    erster = store.first_price_date(conn, isin)
    sym = store.load_price_symbol(conn, isin)
    if erster is None or sym is None or sym.symbol is None:
        return {}
    out: dict[date, Eingabe] = {}
    # stichtage absteigend: (Stichtag, Vorjahresstichtag)
    for t, vorjahr in pairwise(stichtage):
        if erster > vorjahr:
            continue
        ereignisse = store.dividend_events(conn, isin, vorjahr, t)
        out[t] = Eingabe(
            Decimal(len(ereignisse)),
            f"Yahoo {sym.symbol} Dividendenereignisse nach {vorjahr.isoformat()} bis "
            f"{t.isoformat()}"
            + (f": {', '.join(e.date.isoformat() for e in ereignisse)}" if ereignisse else ""),
            "anzahl",
            t,
            None,
            vorjahr,
        )
    return out


def kurse(
    conn: duckdb.DuckDBPyConnection,
    isin: str | None,
    stichtage: list[date],
    berichtswaehrung: str | None,
    unterwaehrungen: dict[str, str],
    max_abstand_tage: int,
    adr: dict[str, str] | None = None,
) -> tuple[dict[str, dict[date, Eingabe]], dict[str, str]]:
    """Kurs je Stichtag (letzter Schlusskurs bis zum Stichtag, höchstens `max_abstand_tage`
    davor) und die Referenzkurse der EZB, die für die Umrechnung nötig sind. Dazu Gründe für
    Lücken. Reine Auswahl, keine Arithmetik."""
    werte: dict[str, dict[date, Eingabe]] = {"kurs": {}}
    if isin is None:
        return werte, {"kurs": "keine ISIN zum Emittenten bekannt"}
    if store.listing_is_receipt(conn, isin):
        # Aktien je Schein: Festlegung, sonst Börsenname (SPEC 5.2 Nr. 11, Bauschritt 7)
        name = (store.listing_info(conn, isin) or ("", ""))[0]
        festgelegt = adr or {}
        verh: Decimal | None
        if isin in festgelegt:
            verh = Decimal(str(festgelegt[isin]))
            quelle = f"festgelegt in state/adr_verhaeltnis.yaml ({isin})"
        else:
            verh = identifiers.adr_verhaeltnis(name)
            quelle = f"Börsenname Deutsche Börse '{name}'"
        if verh is None:
            return werte, {
                "kurs": "Hinterlegungsschein, Aktien je Schein nicht im Börsennamen (festlegen in "
                f"state/adr_verhaeltnis.yaml: {isin}: <Aktien je Schein>, SPEC 5.2 Nr. 11)"
            }
        werte["adr_aktien_je_schein"] = {
            t: Eingabe(verh, f"Aktien je Hinterlegungsschein: {quelle}", "pure", t)
            for t in stichtage
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
    werte["dividenden_yahoo"] = dividenden_yahoo(conn, isin, stichtage)
    luecken = {} if werte["kurs"] else {"kurs": "keine Kurse an den Geschäftsjahresenden"}
    return werte, luecken


@dataclass(frozen=True)
class Branche:
    name: str
    herkunft: str  # Begründung der Zuordnung, erscheint im Rechenweg


def damodaran_branche(
    conn: duckdb.DuckDBPyConnection,
    issuer_id: str,
    isin: str | None,
    boersen: dict[str, list[str]],
    festgelegt: dict[str, str],
) -> Branche | None:
    """Branche bei Damodaran: Lucas Festlegung, sonst über Börse:Kürzel (Yahoo-Symbol oder
    Tickerliste der SEC), sonst die häufigste Branche unter Damodarans Firmen mit demselben
    SIC-Code (Lucas Entscheidung 19.10.2026, ADR 0006)."""
    if isin and isin in festgelegt:
        return Branche(festgelegt[isin], f"festgelegt in state/damodaran_branchen.yaml ({isin})")
    kandidaten: list[str] = []
    sym = store.load_price_symbol(conn, isin) if isin else None
    if sym is not None and sym.symbol:
        basis, _, endung = sym.symbol.rpartition(".")
        if not basis or f".{endung}" not in boersen:
            basis, endung = sym.symbol, ""
        endung = f".{endung}" if endung else ""
        for kuerzel in dict.fromkeys([basis, basis.replace("-", ".")]):
            kandidaten += [f"{b}:{kuerzel}" for b in boersen.get(endung, [])]
    m = store.load_isin_cik(conn).get(isin or "")
    if m is not None and m.ticker:
        kandidaten += [f"{b}:{m.ticker.replace('-', '.')}" for b in boersen.get("", [])]
    treffer = store.damodaran_industry_for(conn, list(dict.fromkeys(kandidaten)))
    if treffer:
        return Branche(treffer[0], f"Damodaran-Firmenliste, {treffer[1]}")
    issuer = store.load_issuer(conn, issuer_id)
    if issuer is not None and issuer.sector_sic:
        s = store.damodaran_industry_by_sic(conn, issuer.sector_sic)
        if s:
            return Branche(
                s[0], f"häufigste Branche bei SIC {issuer.sector_sic} ({s[1]} von {s[2]} Firmen)"
            )
    return None


def _anteil(text: str, quelle: str, t: date) -> Eingabe:
    return Eingabe(Decimal(text), quelle, "anteil", t)


def kapitalmarkt(
    conn: duckdb.DuckDBPyConnection,
    issuer_id: str,
    isin: str | None,
    stichtage: list[date],
    berichtswaehrung: str | None,
    kk_cfg: dict[str, Any],
    boersen: dict[str, list[str]],
    festgelegt: dict[str, str],
) -> tuple[dict[str, dict[date, Eingabe]], dict[str, str], dict[str, Any]]:
    """Eingaben für Kapitalkosten und Reverse-DCF je Stichtag: risikofreier Zins der
    Berichtswährung, Risikoprämie, Branchenbeta, Steuersatz, Branchenaufschlag, Endwachstum.
    Dazu Rating-Tabelle und Kennzeichen als Parameter. Reine Auswahl, keine Arithmetik."""
    werte: dict[str, dict[date, Eingabe]] = {}
    luecken: dict[str, str] = {}
    parameter: dict[str, Any] = {"kapitalkosten": kk_cfg}
    vermerke: list[str] = []
    issuer = store.load_issuer(conn, issuer_id)
    sic = int(issuer.sector_sic) if issuer and issuer.sector_sic else None
    lo, hi = (int(x) for x in kk_cfg["finanz_sic"])
    parameter["finanzfirma"] = sic is not None and lo <= sic <= hi
    parameter["produzent"] = sic is not None and any(
        int(a) <= sic <= int(b) for a, b in kk_cfg["produzent_sic"]
    )
    parameter["sic"] = sic

    # Risikofreier Zins der Berichtswährung
    serie = kk_cfg["zinsreihe"].get(berichtswaehrung or "")
    if serie is None:
        luecken["rf"] = f"kein risikofreier Zins für {berichtswaehrung} (config/kapitalkosten.yaml)"
    else:
        werte["rf"] = {}
        for t in stichtage:
            z = store.rate_on_or_before(conn, serie, t)
            if z is None or dq.kurs_veraltet(z.date, t, int(kk_cfg["zins_max_abstand_tage"])):
                continue
            werte["rf"][t] = Eingabe(
                z.percent,
                f"{z.source} {serie} {z.date.isoformat()} (Rohdatei {z.raw_sha256[:12]})",
                "prozent",
                t,
            )
        if not werte["rf"]:
            luecken["rf"] = f"keine Zinsen {serie} geladen (stockagent markt update)"

    # Risikoprämie (monatlich)
    werte["erp"] = {}
    for t in stichtage:
        e = store.erp_on_or_before(conn, t)
        if e is not None:
            werte["erp"][t] = _anteil(
                str(e.erp),
                f"Damodaran implizite Risikoprämie {e.month:%m.%Y} (Rohdatei {e.raw_sha256[:12]})",
                t,
            )
    if not werte["erp"]:
        luecken["erp"] = "keine Risikoprämie geladen (stockagent markt update)"

    # Branchenbeta und Branchenaufschlag
    branche = damodaran_branche(conn, issuer_id, isin, boersen, festgelegt)
    betas = store.damodaran_meta(conn, "betas_us")
    wacc_meta = store.damodaran_meta(conn, "wacc_us")
    if branche is None:
        luecken["beta_unverschuldet"] = "keine Branche bei Damodaran zugeordnet"
    else:
        parameter["branche_damodaran"] = branche.name
        b = store.industry_beta(conn, branche.name)
        if b is None or b.unlevered_cash is None or betas is None:
            luecken["beta_unverschuldet"] = f"kein Branchenbeta für {branche.name}"
        else:
            quelle = (
                f"Damodaran Betas USA Stand {betas.stand}, Branche {branche.name} "
                f"({branche.herkunft}), unverschuldet um Kasse bereinigt"
            )
            werte["beta_unverschuldet"] = {
                t: Eingabe(b.unlevered_cash, quelle, "faktor", t) for t in stichtage
            }
            vermerke.append(f"BETA_STAND: Branchenbeta Stand {betas.stand} für alle Jahre")
            land = (store.listing_info(conn, isin) or ("", ""))[1] if isin else ""
            if land and land != "US":
                vermerke.append("BETA_USA: US-Branchenbeta, europäische Betas ab Schritt 7")
        if b is not None and b.levered is not None and betas is not None:
            # Banken und Versicherer: Beta der Branche wie gemessen, ohne Umrechnung über die
            # Verschuldung (Schulden sind dort Rohstoff des Geschäfts, SPEC 3.11, ADR 0010)
            quelle_l = (
                f"Damodaran Betas USA Stand {betas.stand}, Branche {branche.name} "
                f"({branche.herkunft}), Beta der Branche"
            )
            werte["beta_branche"] = {
                t: Eingabe(b.levered, quelle_l, "faktor", t) for t in stichtage
            }
        kd = store.industry_cost_of_debt(conn, branche.name)
        if kd is not None and wacc_meta is not None and wacc_meta.stand:
            monat = datetime.strptime(wacc_meta.stand, "%B %Y").date()
            e = store.erp_on_or_before(conn, monat)
            if e is not None and e.tbond is not None:
                werte["kd_branche"] = {
                    t: Eingabe(
                        kd,
                        f"Damodaran Kapitalkosten USA Stand {wacc_meta.stand}, Branche "
                        f"{branche.name}, Fremdkapitalkosten vor Steuern",
                        "prozent",
                        t,
                    )
                    for t in stichtage
                }
                werte["rf_damodaran"] = {
                    t: _anteil(
                        str(e.tbond),
                        f"Damodaran Zins 10-jährige Treasury {e.month:%m.%Y} (Stand der Tabelle)",
                        t,
                    )
                    for t in stichtage
                }

    # Steuersatz und Endwachstum aus config/kapitalkosten.yaml
    land = (store.listing_info(conn, isin) or ("", ""))[1] if isin else ""
    saetze = kk_cfg["steuersatz"]
    satz, herkunft = (saetze[land], land) if land in saetze else (saetze["standard"], "standard")
    werte["steuersatz"] = {
        t: _anteil(str(satz), f"config/kapitalkosten.yaml steuersatz {herkunft}", t)
        for t in stichtage
    }
    werte["endwachstum_max"] = {
        t: _anteil(str(kk_cfg["endwachstum_max"]), "config/kapitalkosten.yaml endwachstum_max", t)
        for t in stichtage
    }
    ratings = store.rating_table(conn, "finanz" if parameter["finanzfirma"] else "nichtfinanz")
    rmeta = store.damodaran_meta(conn, "ratings")
    parameter["ratings"] = [
        {
            "art": z.kind,
            "ab": str(z.coverage_from),
            "bis": str(z.coverage_to),
            "rating": z.rating,
            "aufschlag": str(z.spread_percent),
            "stand": rmeta.stand if rmeta else "",
        }
        for z in ratings
    ]
    parameter["vermerke_kapitalkosten"] = tuple(vermerke)
    return werte, luecken, parameter


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
    kk_cfg: dict[str, Any] | None = None,
) -> Reihen:
    """Jahresreihen aller internen Größen aus `cmap['us-gaap']` für bis zu `max_jahre` Jahre.
    Mit `isin` und `kurs_cfg` (Abschnitt `kurse` aus metrics.yaml plus Unterwährungen) auch
    Schlusskurse und Wechselkurse an den Stichtagen."""
    facts = store.pit_query(conn, as_of=as_of, issuer_id=issuer_id)
    stichtage = quality.jahresstichtage(facts, quality.kern_konzepte(cmap))[:max_jahre]
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
    # Investitionen als ein Posten mit immateriellen Werten (SAP, BP): diese nicht doppelt abziehen
    gesamt = tuple(cmap.get("capex_inkl_immateriell", []))
    for t, e in werte.get("capex", {}).items():
        if any(k in e.quelle for k in gesamt):
            werte.get("capex_intangibles", {}).pop(t, None)
    # IFRS: Leasing ohne eigene kurz- und langfristige Bilanzzeile steckt in den Finanzschulden
    # (Shell: Borrowings enthält die Leasingverbindlichkeiten). Dann nicht noch einmal addieren
    leasing_in_schulden = []
    for t, e in list(werte.get("lease_finance", {}).items()):
        if e.quelle.startswith("ifrs-full:LeaseLiabilities@") and not (
            t in werte.get("lease_finance_current", {})
            or t in werte.get("lease_finance_noncurrent", {})
        ):
            del werte["lease_finance"][t]
            leasing_in_schulden.append(t)
    werte["shares_diluted"] = abgeleitet.aktien_aus_eps(
        werte.get("shares_diluted", {}), werte.get("net_income", {}), werte.get("eps_diluted", {})
    )
    werte["revenue"] = abgeleitet.umsatz_aus_bruttoergebnis(
        werte.get("revenue", {}), werte.get("gross_profit", {}), werte.get("cost_of_revenue", {})
    )
    luecken: dict[str, str] = {}
    parameter: dict[str, Any] = {"leasing_in_finanzschulden": tuple(leasing_in_schulden)}
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
            dict(kurs_cfg.get("adr", {})),
        )
        werte.update(kurs_werte)
        parameter["unterwaehrungen"] = unter
    if kk_cfg is not None:
        umsatz = next(iter(werte.get("revenue", {}).values()), None)
        kk_werte, kk_luecken, kk_parameter = kapitalmarkt(
            conn,
            issuer_id,
            isin,
            list(stichtage),
            umsatz.waehrung if umsatz else None,
            kk_cfg,
            dict(kk_cfg.get("boersen", {})),
            dict(kk_cfg.get("festgelegt", {})),
        )
        werte.update(kk_werte)
        luecken.update(kk_luecken)
        parameter.update(kk_parameter)
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


def ttm(
    conn: duckdb.DuckDBPyConnection,
    issuer_id: str,
    as_of: datetime,
    cmap: dict[str, Any],
    basis: Reihen,
) -> tuple[date, dict[str, Strom], dict[str, Eingabe]] | None:
    """Teile für TTM-Werte zum letzten Quartal nach dem letzten Geschäftsjahr (SPEC 3.4 Nr. 1):
    je Strom Geschäftsjahr, Zeitraum seit Jahresbeginn und derselbe Zeitraum im Vorjahr, je
    Stand der Wert am Quartalsende. None, wenn seit dem Geschäftsjahr kein Quartal gemeldet ist.
    Reine Auswahl, gerechnet wird in `core/ttm.py`."""
    if not basis.stichtage or not basis.hat("revenue", basis.stichtage[0]):
        return None
    gj = basis.stichtage[0]
    gj_umsatz = basis.hole("revenue", gj)
    if gj_umsatz.periode_start is None:
        return None
    facts = [
        f
        for f in store.pit_query(conn, as_of=as_of, issuer_id=issuer_id)
        if f.form not in ANNUAL_FORMS
    ]

    def nah(a: date | None, b: date) -> bool:
        return a is not None and dq.dauer_tage(min(a, b), max(a, b)) <= 8

    umsatz = concepts.resolve(facts, cmap["us-gaap"]["revenue"])
    quartale = [e for (s, e) in umsatz if e > gj and s is not None and dq.dauer_tage(gj, s) <= 9]
    if not quartale:
        return None
    quartal = max(quartale)
    stroeme: dict[str, Strom] = {}
    staende: dict[str, Eingabe] = {}
    for name, liste in cmap["us-gaap"].items():
        je = concepts.resolve(facts, liste)
        stand = je.get((None, quartal))
        if stand is not None:
            staende[name] = eingabe(stand)
            continue
        if name == "shares_diluted":
            # Aktienzahl: Durchschnitt des letzten Quartals
            q3 = [f for (s, e), f in je.items() if e == quartal and dq.periode_passt(s, e, "Q")]
            if q3:
                staende[name] = eingabe(q3[0])
            continue
        if gj not in basis.werte.get(name, {}):
            continue
        ytd = next(
            (
                f
                for (s, e), f in je.items()
                if e == quartal and s is not None and dq.dauer_tage(gj, s) <= 9
            ),
            None,
        )
        vj = next(
            (
                f
                for (s, e), f in je.items()
                if s is not None
                and nah(s, gj_umsatz.periode_start)
                and e < quartal
                and 358 <= dq.dauer_tage(e, quartal) <= 374
            ),
            None,
        )
        if ytd is not None and vj is not None:
            stroeme[name] = Strom(basis.werte[name][gj], eingabe(ytd), eingabe(vj))
    return quartal, stroeme, staende


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
    kk = basis.parameter.get("kapitalkosten")
    if kk:
        # Kapitalkosten mit dem Zins und der Risikoprämie von heute
        serie = kk["zinsreihe"].get(umsatz.waehrung if umsatz else "")
        z = store.rate_on_or_before(conn, serie, heute) if serie else None
        if z is not None and not dq.kurs_veraltet(z.date, heute, int(kk["zins_max_abstand_tage"])):
            neu["rf"] = {
                stichtag: Eingabe(
                    z.percent,
                    f"{z.source} {serie} {z.date.isoformat()} (Rohdatei {z.raw_sha256[:12]})",
                    "prozent",
                    stichtag,
                )
            }
        e = store.erp_on_or_before(conn, heute)
        if e is not None:
            neu["erp"] = {
                stichtag: _anteil(
                    str(e.erp),
                    f"Damodaran implizite Risikoprämie {e.month:%m.%Y} "
                    f"(Rohdatei {e.raw_sha256[:12]})",
                    stichtag,
                )
            }
    werte = {name: dict(je) for name, je in basis.werte.items()}
    for name, je in neu.items():
        werte.setdefault(name, {}).update(je)
    return replace(basis, werte=werte)


def mit_parametern(basis: Reihen, parameter: dict[str, Any]) -> Reihen:
    """Feste Annahmen aus `config/metrics.yaml` (Abschnitt `parameter`) als Eingaben mit Quelle
    an jedem Stichtag, Name `parameter_<name>` (Bauschritt 8). Reine Auswahl."""
    werte = {name: dict(je) for name, je in basis.werte.items()}
    for name, wert in parameter.items():
        werte[f"parameter_{name}"] = {
            t: Eingabe(Decimal(str(wert)), f"config/metrics.yaml parameter.{name}", "pure", t)
            for t in basis.stichtage
        }
    return replace(basis, werte=werte)
