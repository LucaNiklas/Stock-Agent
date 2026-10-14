"""Hinweise der Abteilung Berechnung an die Agenten (SPEC 8.5).

Reine Regelauswertung ohne Arithmetik: Vergleich berechneter Werte mit Schwellen aus `config/`,
Warnungen der Prüfpunkte und Flags der Datenqualität. Jeder Hinweis nennt den Agenten, der ihn
ab Bauschritt 6 als Auftrag bekommt, und den Anlass. Gespeichert wird in `data/store.py`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from stockagent.core.anzeige import formatiere
from stockagent.core.calc import Ergebnis


@dataclass(frozen=True)
class Kennzahlwert:
    """Eine gespeicherte Rechnung: Jahreswert (`statistik` = "wert") oder Trendstatistik."""

    metric_id: str
    metric_version: str
    statistik: str
    period_end: date
    ergebnis: Ergebnis


@dataclass(frozen=True)
class Hinweis:
    regel: str
    an: str
    abteilung: str
    anlass: str
    metric_id: str | None
    period_end: date | None
    detail: str


class Flag(Protocol):
    @property
    def check_id(self) -> str: ...
    @property
    def severity(self) -> str: ...
    @property
    def period_end(self) -> date | None: ...
    @property
    def concept(self) -> str | None: ...
    @property
    def detail(self) -> str: ...


def _schwelle(metrics_cfg: Mapping[str, Any], metric_id: str, name: str) -> Decimal:
    for m in metrics_cfg["metrics"]:
        if m["id"] == metric_id:
            return Decimal(str(m["schwellen"][name]))
    raise KeyError(f"Schwelle {name} für {metric_id} fehlt in config/metrics.yaml")


def _erfuellt(wert: Decimal, vergleich: str, schwelle: Decimal) -> bool:
    if vergleich == "ueber":
        return wert > schwelle
    if vergleich == "unter":
        return wert < schwelle
    raise ValueError(f"Unbekannter Vergleich: {vergleich}")


Treffer = tuple[str | None, date | None, str]


def _treffer(
    regel: Mapping[str, Any],
    werte: list[Kennzahlwert],
    flags: list[Flag],
    stichtag: date,
    metrics_cfg: Mapping[str, Any],
) -> list[Treffer]:
    if "kennzahl" in regel:
        schwelle = _schwelle(metrics_cfg, regel["kennzahl"], regel["schwelle"])
        return [
            (
                w.metric_id,
                w.period_end,
                f"Wert {formatiere(w.ergebnis.wert, 'faktor', 2)} "
                f"{'über' if regel['vergleich'] == 'ueber' else 'unter'} {schwelle}",
            )
            for w in werte
            if w.metric_id == regel["kennzahl"]
            and w.statistik == "wert"
            and w.period_end == stichtag
            and w.ergebnis.wert is not None
            and _erfuellt(w.ergebnis.wert, regel["vergleich"], schwelle)
        ]
    if "trend_warnung" in regel:
        return [
            (
                w.metric_id,
                w.period_end,
                f"robuster z-Wert {formatiere(w.ergebnis.wert, 'faktor', 1)} gegen die Vorjahre "
                f"({'; '.join(w.ergebnis.warnungen)})",
            )
            for w in werte
            if w.statistik == regel["trend_warnung"] and w.ergebnis.warnungen
        ]
    if "ungereimtheit" in regel:
        return [
            (w.metric_id, w.period_end, str(w.ergebnis.grund))
            for w in werte
            if w.ergebnis.ungereimtheit == regel["ungereimtheit"]
        ]
    if "dq_stufe" in regel:
        return [
            (None, f.period_end, f"{f.check_id} {f.concept or ''}: {f.detail}")
            for f in flags
            if f.severity == regel["dq_stufe"]
        ]
    if "dq_pruefung" in regel:
        return [
            (None, f.period_end, f"{f.concept or ''}: {f.detail}")
            for f in flags
            if f.check_id == regel["dq_pruefung"] and f.severity != "ok"
        ]
    raise ValueError(f"Regel {regel['id']} ohne Bedingung")


def ableiten(
    werte: Iterable[Kennzahlwert],
    flags: Iterable[Flag],
    stichtag: date,
    regeln_cfg: Mapping[str, Any],
    metrics_cfg: Mapping[str, Any],
) -> list[Hinweis]:
    """Hinweise zum Stichtag. Schwellenregeln gelten für den Jahreswert des Stichtags, Prüfpunkt-
    Regeln für alle gespeicherten Rechnungen, Datenqualitätsregeln für alle Flags."""
    w, f = list(werte), list(flags)
    return [
        Hinweis(regel["id"], regel["an"], regel["abteilung"], regel["anlass"], m, p, detail)
        for regel in regeln_cfg["regeln"]
        for m, p, detail in _treffer(regel, w, f, stichtag, metrics_cfg)
    ]
