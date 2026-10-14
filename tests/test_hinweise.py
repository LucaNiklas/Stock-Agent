"""Hinweise der Berechnung an die Agenten (config/hinweise.yaml)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import yaml

from stockagent.core import hinweise
from stockagent.core.calc import Ergebnis
from stockagent.core.hinweise import Kennzahlwert
from stockagent.data.store import DqFlag
from tests.metrics.apple import ROOT

REGELN = yaml.safe_load((ROOT / "config" / "hinweise.yaml").read_text("utf-8"))
METRICS = yaml.safe_load((ROOT / "config" / "metrics.yaml").read_text("utf-8"))
T = date(2026, 1, 31)


def _w(metric_id: str, wert: str | None, statistik: str = "wert", **kw: object) -> Kennzahlwert:
    e = Ergebnis(
        metric_id,
        None if wert is None else Decimal(wert),
        kw.get("grund"),  # type: ignore[arg-type]
        kw.get("inc"),  # type: ignore[arg-type]
        tuple(kw.get("warnungen", ())),  # type: ignore[arg-type]
        {},
    )
    return Kennzahlwert(metric_id, "1.0", statistik, T, e)


def _regeln(werte: list[Kennzahlwert], flags: list[DqFlag] | None = None) -> list[str]:
    return [h.regel for h in hinweise.ableiten(werte, flags or [], T, REGELN, METRICS)]


def test_thresholds_from_metrics_config() -> None:
    werte = [
        _w("beneish_m_score", "-1.7763"),  # PagerDuty 2026
        _w("altman_z_double_prime", "1.0634"),
        _w("piotroski_f_score", "6"),  # genau 6 gilt als solide
        _w("sloan_accruals", "0.1"),  # genau auf der Schwelle: kein Hinweis
    ]
    assert _regeln(werte) == ["H-01", "H-02"]
    (h,) = hinweise.ableiten(werte[:1], [], T, REGELN, METRICS)
    assert h.an == "F1" and h.detail == "Wert -1,78 über -1.78"


def test_threshold_only_for_latest_year() -> None:
    alt = _w("beneish_m_score", "-1.0")
    alt = Kennzahlwert(alt.metric_id, "1.0", "wert", date(2025, 1, 31), alt.ergebnis)
    assert _regeln([alt]) == []


def test_trend_warning_and_stopped_calculation() -> None:
    werte = [
        _w("ebit_margin", "5.2", "plausibilitaet", warnungen=["CP-05: |z| höchstens 4"]),
        _w("roe", None, grund="CP-03: Summe passt nicht", inc="INC-15"),
        _w("roic", None, grund="Nicht definiert: Investiertes Kapital nicht positiv"),
    ]
    assert _regeln(werte) == ["H-05", "H-06"]


def test_data_quality_flags() -> None:
    flags = [
        DqFlag("sec:1", "DQ-01", "stopp", T, "us-gaap:Assets", "Bilanz geht nicht auf"),
        DqFlag("sec:1", "DQ-06", "warnung", T, "us-gaap:Revenues", "Ausreißer"),
        DqFlag("sec:1", "DQ-07", "ok", None, None, "keine Änderungen"),
    ]
    assert _regeln([], flags) == ["H-07", "H-08"]


def test_every_rule_names_agent_and_department() -> None:
    agenten = {"A1", "A3", "A4", "F1"}
    for r in REGELN["regeln"]:
        assert r["an"] in agenten and r["abteilung"] in ("Recherche", "Auswertung", "Prüfung")
