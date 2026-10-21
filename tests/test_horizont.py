"""Anlagehorizont (ADR 0011): Momentum-Säule und Note je Horizont."""

from __future__ import annotations

import json
import shutil
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from stockagent import bewertung
from stockagent.core import marktrisiko, momentum, note
from stockagent.data import store
from stockagent.paths import Paths
from tests.sec_fixtures import ROOT
from tests.test_bewertung import FIRMEN, NOW, Attrappe, _seed


def _handelstage(anzahl: int, bis: date) -> list[date]:
    tage: list[date] = []
    d = bis
    while len(tage) < anzahl:
        if d.weekday() < 5:
            tage.append(d)
        d -= timedelta(days=1)
    return sorted(tage)


def test_momentum_by_hand() -> None:
    """300 Handelstage, Kurs am Tag i = 100 + i. Letzter Tag i = 299.
    12-1: Kurs vor 21 Tagen (i = 278) / vor 252 Tagen (i = 47) - 1 = 378 / 147 - 1 = 1,5714.
    6-1: 378 / Kurs vor 126 Tagen (i = 173, Kurs 273) - 1 = 0,3846.
    Nähe zum Hoch: 399 / 399 = 1."""
    tage = _handelstage(300, date(2026, 10, 16))
    reihe = [marktrisiko.Tag(d, Decimal(100 + i), 1000) for i, d in enumerate(tage)]
    m, _ = momentum.momentum("x", reihe, date(2026, 10, 19), 7)
    vier = Decimal("0.0001")
    assert m["momentum_12_1"] is not None and m["momentum_12_1"].quantize(vier) == Decimal("1.5714")
    assert m["momentum_6_1"] is not None and m["momentum_6_1"].quantize(vier) == Decimal("0.3846")
    assert m["naehe_52w_hoch"] == 1
    # Veralteter letzter Kurs: kein Momentum
    alt, weg_alt = momentum.momentum("x", reihe, date(2026, 11, 30), 7)
    assert alt["momentum_12_1"] is None and "zu alt" in str(weg_alt["momentum_12_1"])
    # Zu kurze Reihe: 12-1 fehlt, 6-1 geht
    kurz, _ = momentum.momentum("x", reihe[-200:], date(2026, 10, 19), 7)
    assert kurz["momentum_12_1"] is None and kurz["momentum_6_1"] is not None


def test_trend_and_report_reaction() -> None:
    """Kurs am Tag i = 100 + i, 300 Tage. 200-Tage-Linie = Mittel von 200 bis 399 = 299,5,
    Abstand 399 / 299,5 - 1 = 0,3322. Bericht am Handelstag i = 290: letzter Kurs davor 389
    (i = 289), zweiter Handelstag danach 392 (i = 292): 392 / 389 - 1 = 0,771 %."""
    tage = _handelstage(300, date(2026, 10, 16))
    reihe = [marktrisiko.Tag(d, Decimal(100 + i), 1000) for i, d in enumerate(tage)]
    bericht = tage[290]
    m, _ = momentum.momentum("x", reihe, date(2026, 10, 19), 7, bericht, 120)
    assert m["abstand_ma200"] is not None
    assert m["abstand_ma200"].quantize(Decimal("0.0001")) == Decimal("0.3322")
    assert m["reaktion_bericht"] is not None
    assert m["reaktion_bericht"].quantize(Decimal("0.00001")) == Decimal("0.00771")
    alt, weg_alt = momentum.momentum("x", reihe, date(2026, 10, 19), 7, date(2026, 1, 2), 120)
    assert alt["reaktion_bericht"] is None and "älter als 120" in str(weg_alt["reaktion_bericht"])


def test_weights_per_horizon_keep_ratios() -> None:
    basis = {
        "qualitaet": "0.25",
        "bewertung": "0.25",
        "stabilitaet": "0.15",
        "wachstum": "0.15",
        "kapitalallokation": "0.10",
        "insider": "0.10",
    }
    g = note.gewichte_horizont(basis, Decimal("0.40"))
    assert g["momentum"] == Decimal("0.40") and g["qualitaet"] == Decimal("0.15")
    assert sum(g.values()) == 1
    assert note.gewichte_horizont(basis, Decimal(0))["qualitaet"] == Decimal("0.25")
    with pytest.raises(ValueError):
        note.gewichte_horizont(basis, Decimal("1.5"))


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    shutil.copytree(ROOT / "config", tmp_path / "config")
    p = Paths(tmp_path)
    _seed(p)
    return p


def _kurse(paths: Paths, steigend_bis_auf: str) -> None:
    """Firma n steigt um n Promille je Handelstag. Die Firma `steigend_bis_auf` fällt dagegen
    um 2 Promille je Tag: schlechtestes Momentum der Gruppe."""
    tage = _handelstage(300, NOW.date() - timedelta(days=1))
    conn = store.connect(paths.db)
    try:
        for n, (isin, _) in enumerate(FIRMEN, start=1):
            schritt = Decimal(-2 if isin == steigend_bis_auf else n) / 1000
            kurs, rows = Decimal(100), []
            for d in tage:
                rows.append(store.PriceRow(isin, d, kurs, None, 10_000, "EUR", "X", "test"))
                kurs = kurs * (1 + schritt)
            store.save_prices(conn, rows, [], "sha", NOW)
    finally:
        conn.close()


def test_grade_per_horizon(paths: Paths) -> None:
    """Firma 20 ist in allen Kennzahlen der Scorecard die beste (Perzentil 97,5), hat aber das
    schlechteste Kursmomentum (Perzentil 2,5 in den drei Kurskennzahlen). Insider ohne Daten.
    lang: Momentum 0 -> 97,5 (A).
    mittel: übrige Säulen 0,9 * 0,85 = 0,765, Momentum 0,15:
            (0,765 * 97,5 + 0,15 * 2,5) / 0,915 = 81,93 (A).
    kurz:   (0,9 * 0,6 * 97,5 + 0,40 * 2,5) / 0,94 = 57,07 (C)."""
    isin = FIRMEN[-1][0]
    _kurse(paths, isin)
    erg = bewertung.bewerten(paths, isin, lader=Attrappe().lader(), now=NOW)
    assert erg.grade is not None
    h = json.loads(erg.grade.detail_json or "{}")["horizonte"]
    assert Decimal(h["lang"]["score"]) == Decimal("97.5") and h["lang"]["note"] == "A"
    assert Decimal(h["mittel"]["score"]).quantize(Decimal("0.01")) == Decimal("81.93")
    assert Decimal(h["kurz"]["score"]).quantize(Decimal("0.01")) == Decimal("57.07")
    assert h["kurz"]["note"] == "C" and h["mittel"]["note"] == "A"
    # Hauptnote = Standardhorizont mittel
    assert erg.note == "A" and erg.grade.score is not None
    assert erg.grade.score.quantize(Decimal("0.01")) == Decimal("81.93")
    conn = store.connect(paths.db)
    try:
        assert [n for _, n in store.snapshot_grades_horizont(conn, isin, "kurz")] == ["C"]
    finally:
        conn.close()


def test_short_horizon_needs_momentum_for_attraktiv(paths: Paths) -> None:
    """Mit gutem Kursmomentum ist die Firma in allen Horizonten A."""
    isin = FIRMEN[-1][0]
    _kurse(paths, "keine")  # Firma 20 hat jetzt auch das beste Momentum
    erg = bewertung.bewerten(paths, isin, lader=Attrappe().lader(), now=NOW)
    assert erg.grade is not None
    h = json.loads(erg.grade.detail_json or "{}")["horizonte"]
    assert {v["note"] for v in h.values()} == {"A"}
    # 12-1, 6-1 und Abstand zur 200-Tage-Linie Perzentil 97,5. Beim 52-Wochen-Hoch stehen alle
    # steigenden Firmen auf ihrem Hoch (Wert 1, Gleichstand aller 20): Perzentil
    # (0 + 0,5 * 20) / 20 * 100 = 50. Kursreaktion auf den Bericht fehlt (keine Berichte in der
    # Testdatenbank). Säule (3 * 97,5 + 50) / 4 = 85,625
    mom = Decimal(h["kurz"]["saeulen"]["momentum"])
    assert mom == Decimal("85.625")


def test_weak_momentum_blocks_attraktiv_for_short_horizon() -> None:
    """Regel aus config/horizonte.yaml: im Horizont kurz wird Attraktiv zu Beobachten, wenn die
    Momentum-Säule unter 50 liegt. Geprüft an der Konfiguration, die bewertung.py liest."""
    import yaml

    h = yaml.safe_load((ROOT / "config" / "horizonte.yaml").read_text("utf-8"))
    assert h["horizonte"]["kurz"]["kategorie_momentum_mindest"] == 50
    assert "kategorie_momentum_mindest" not in h["horizonte"]["lang"]
    assert h["standard"] in h["horizonte"]
    anteile = [Decimal(v["momentum_anteil"]) for v in h["horizonte"].values()]
    assert anteile == sorted(anteile, reverse=True)  # kurz > mittel > lang


def test_dashboard_horizon_filter_and_sort(paths: Paths) -> None:
    """Firma 20 mit schlechtem Kursmomentum: im Horizont kurz Note C, mittel A (siehe oben).
    Firma 19 ebenfalls bewertet. Filter Note A je Horizont, Sortierung nach Gesamtwert."""
    from stockagent.dashboard import app as dashboard

    isin = FIRMEN[-1][0]
    _kurse(paths, isin)
    bewertung.bewerten(paths, isin, lader=Attrappe().lader(), now=NOW)
    bewertung.bewerten(paths, FIRMEN[-2][0], lader=Attrappe().lader(), now=NOW)
    daten = dashboard.Daten(paths)
    mittel = dashboard.liste(daten, {"note": "A"})
    assert mittel["horizont"] == "mittel" and isin in [z["isin"] for z in mittel["zeilen"]]
    kurz = dashboard.liste(daten, {"note": "A", "horizont": "kurz"})
    assert isin not in [z["isin"] for z in kurz["zeilen"]]
    assert dict(dashboard.liste(daten, {"horizont": "kurz"})["facetten"]["note"])["C"] >= 1
    sortiert = dashboard.liste(daten, {"bewertet": "1", "sortierung": "wert", "horizont": "kurz"})
    werte = [float(z["score"]) for z in sortiert["zeilen"]]
    assert werte == sorted(werte, reverse=True) and len(werte) == 2
    assert sortiert["horizonte"]["kurz"]["mindest"] == 50
    assert dashboard.freitext("kurzfristig Note A", daten) == {"horizont": "kurz", "note": "A"}
    assert dashboard.freitext("1 bis 5 Jahre halten", daten)["horizont"] == "mittel"
