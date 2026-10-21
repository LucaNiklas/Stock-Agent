"""Zinsen und Damodaran-Daten laden (Bauschritt 4, Abteilung Recherche, SPEC 3.6, 7.3)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import yaml

from stockagent.core import dq
from stockagent.data import store
from stockagent.data.http import fetch
from stockagent.data.sources import damodaran, rates
from stockagent.paths import Paths


@dataclass
class ZinsErgebnis:
    je_serie: dict[str, tuple[int, date | None]] = field(default_factory=dict)
    uebersprungen: list[str] = field(default_factory=list)


def _cfg(paths: Paths) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((paths.config / "sources.yaml").read_text("utf-8"))
    return data


def zinsen_update(
    paths: Paths,
    *,
    refresh: bool = False,
    fetcher: Callable[..., bytes] = fetch,
    now: datetime | None = None,
) -> ZinsErgebnis:
    """10-jährige Zinsen für EUR (Bundesbank) und USD (Treasury). Beim ersten Mal ab `start`."""
    now = now or datetime.now(UTC)
    cfg = _cfg(paths)
    zcfg = cfg["zinsen"]
    start = date.fromisoformat(str(zcfg["start"]))
    client = rates.ZinsClient(zcfg, cfg["user_agent"], paths.raw, fetcher=fetcher, now=lambda: now)
    out = ZinsErgebnis()
    conn = store.connect(paths.db)
    try:
        for serie, quelle in (("rf_10y_EUR", "bundesbank"), ("rf_10y_USD", "treasury")):
            letzter = store.last_rate(conn, serie)
            if (
                letzter
                and not refresh
                and dq.juenger_als(letzter[1].date(), now.date(), int(zcfg["aktuell_tage"]))
            ):
                out.uebersprungen.append(serie)
                out.je_serie[serie] = (0, letzter[0])
                continue
            ab = letzter[0] if letzter and not refresh else start
            abrufe = (
                [client.bundesbank(ab)]
                if quelle == "bundesbank"
                else [client.treasury(j) for j in range(ab.year, now.year + 1)]
            )
            neu = 0
            bis: date | None = letzter[0] if letzter else None
            for a in abrufe:
                rows = [(z.datum, z.serie, z.prozent) for z in a.zinsen if z.datum >= start]
                store.save_rates(conn, rows, quelle, a.raw.sha256, now)
                neu += len(rows)
                tage = [r[0] for r in rows] + ([bis] if bis else [])
                bis = max(tage) if tage else None
            out.je_serie[serie] = (neu, bis)
    finally:
        conn.close()
    return out


@dataclass
class DamodaranErgebnis:
    je_datensatz: dict[str, tuple[int, str | None]] = field(default_factory=dict)
    uebersprungen: list[str] = field(default_factory=list)


_TEXT = "VARCHAR"


def damodaran_update(
    paths: Paths,
    *,
    refresh: bool = False,
    fetcher: Callable[..., bytes] = fetch,
    now: datetime | None = None,
) -> DamodaranErgebnis:
    now = now or datetime.now(UTC)
    cfg = _cfg(paths)
    dcfg = cfg["damodaran"]
    client = damodaran.DamodaranClient(
        dcfg, cfg["user_agent"], paths.raw, fetcher=fetcher, now=lambda: now
    )
    out = DamodaranErgebnis()
    conn = store.connect(paths.db)
    try:

        def frisch(name: str) -> bool:
            meta = store.damodaran_meta(conn, name)
            return (
                meta is not None
                and not refresh
                and dq.juenger_als(meta.retrieved_at.date(), now.date(), int(dcfg["aktuell_tage"]))
            )

        def speichere(
            name: str,
            schluessel: str,
            table: str,
            types: dict[str, str],
            umwandeln: Callable[[bytes], tuple[list[list[Any]], str | None]],
            replace_all: bool = True,
        ) -> None:
            if frisch(name):
                out.uebersprungen.append(name)
                return
            a = client.hole(schluessel)
            rows, stand = umwandeln(a.raw)
            store.save_damodaran(
                conn,
                name,
                table,
                types,
                rows,
                stand=stand,
                raw_sha256=a.ref.sha256,
                url=str(dcfg[schluessel]),
                retrieved_at=now,
                replace_all=replace_all,
            )
            out.je_datensatz[name] = (len(rows), stand)

        def betas(raw: bytes) -> tuple[list[list[Any]], str | None]:
            return [
                [
                    b.branche,
                    b.firmen,
                    *(
                        str(v) if v is not None else ""
                        for v in (
                            b.beta,
                            b.de_prozent,
                            b.steuer_prozent,
                            b.beta_unverschuldet,
                            b.kasse_prozent,
                            b.beta_unverschuldet_kasse,
                        )
                    ),
                ]
                for b in damodaran.parse_betas(raw)
            ], damodaran.stand(raw)

        speichere(
            "betas_us",
            "betas_url",
            "damodaran_betas",
            {
                "industry": _TEXT,
                "firms": "INTEGER",
                "beta": _TEXT,
                "de_percent": _TEXT,
                "tax_percent": _TEXT,
                "unlevered": _TEXT,
                "cash_percent": _TEXT,
                "unlevered_cash": _TEXT,
            },
            betas,
        )

        def ratings(raw: bytes) -> tuple[list[list[Any]], str | None]:
            return [
                [r.art, str(r.deckung_ab), str(r.deckung_bis), r.rating, str(r.aufschlag_prozent)]
                for r in damodaran.parse_ratings(raw)
            ], damodaran.stand(raw)

        speichere(
            "ratings",
            "ratings_url",
            "damodaran_ratings",
            {
                "kind": _TEXT,
                "coverage_from": _TEXT,
                "coverage_to": _TEXT,
                "rating": _TEXT,
                "spread_percent": _TEXT,
            },
            ratings,
        )

        def wacc(raw: bytes) -> tuple[list[list[Any]], str | None]:
            zeilen = damodaran.tabelle(raw)
            kopf = next((i for i, z in enumerate(zeilen) if z and z[0] == "Industry Name"), None)
            if kopf is None or "Cost of Debt" not in zeilen[kopf]:
                raise damodaran.DamodaranFormatError("wacc.html ohne Spalte Cost of Debt")
            i = zeilen[kopf].index("Cost of Debt")
            rows = [
                [z[0], z[i].replace("%", "").strip()]
                for z in zeilen[kopf + 1 :]
                if len(z) > i and z[0] and z[i]
            ]
            return rows, damodaran.stand(raw)

        speichere(
            "wacc_us",
            "wacc_url",
            "damodaran_wacc",
            {"industry": _TEXT, "cost_of_debt_percent": _TEXT},
            wacc,
        )

        def erp(raw: bytes) -> tuple[list[list[Any]], str | None]:
            werte = damodaran.parse_erp(raw, str(dcfg["erp_spalte"]))
            sha = hashlib.sha256(raw).hexdigest()
            letzter = werte[-1].monat.isoformat() if werte else None
            return [
                [e.monat, str(e.erp), str(e.tbond) if e.tbond is not None else "", sha]
                for e in werte
            ], letzter

        speichere(
            "erp",
            "erp_url",
            "damodaran_erp",
            {"month": "DATE", "erp": _TEXT, "tbond": _TEXT, "raw_sha256": _TEXT},
            erp,
            replace_all=False,
        )

        def firmen(raw: bytes) -> tuple[list[list[Any]], str | None]:
            return [
                [f.boerse_kuerzel, f.firma, f.branche, f.sic or "", f.land or ""]
                for f in damodaran.parse_indname(raw)
            ], None

        speichere(
            "firms",
            "firms_url",
            "damodaran_firms",
            {
                "ticker": _TEXT,
                "firm": _TEXT,
                "industry": _TEXT,
                "sic": _TEXT,
                "country": _TEXT,
            },
            firmen,
        )
    finally:
        conn.close()
    return out
