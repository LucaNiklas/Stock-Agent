"""Bauschritt 5: Note, Konfidenz, Risiko, Kategorie (core/note.py, SPEC 6).

Kleine Beispiele mit Handrechnung. Die Gruppe hat 4 Titel plus die Firma selbst.
"""

from __future__ import annotations

from decimal import Decimal

import yaml

from stockagent.core import marktrisiko, note, sektoren, vergleichsgruppe
from stockagent.core.calc import Rechenweg
from tests.sec_fixtures import ROOT

SCORING = yaml.safe_load((ROOT / "config" / "scoring.yaml").read_text("utf-8"))
SECTORS = yaml.safe_load((ROOT / "config" / "sectors.yaml").read_text("utf-8"))
SCORECARDS = yaml.safe_load((ROOT / "config" / "scorecards.yaml").read_text("utf-8"))

KARTE = {
    "saeulen": {
        "qualitaet": [{"kennzahl": "roic", "statistik": "wert", "richtung": "hoch"}],
        "bewertung": [{"kennzahl": "ev_ebit", "statistik": "aktuell", "richtung": "niedrig"}],
        "stabilitaet": [],
        "wachstum": [],
        "kapitalallokation": [],
        "insider": [],
    }
}


def _d(**kw: str | None) -> dict[tuple[str, str], Decimal | None]:
    out: dict[tuple[str, str], Decimal | None] = {}
    for k, v in kw.items():
        name, stat = k.rsplit("__", 1)
        out[(name, stat)] = Decimal(v) if v is not None else None
    return out


GRUPPE = [
    _d(roic__wert="0.05", ev_ebit__aktuell="10"),
    _d(roic__wert="0.10", ev_ebit__aktuell="15"),
    _d(roic__wert="0.15", ev_ebit__aktuell="20"),
    _d(roic__wert="0.20", ev_ebit__aktuell="25"),
]


def test_percentile_and_weighted_score() -> None:
    """ROIC 0,18: 3 kleiner, 1 gleich (die Firma selbst) von 5 -> (3 + 0,5) / 5 * 100 = 70.
    EV/EBIT 12: 1 kleiner (10), 1 gleich -> 30, niedriger besser -> 70. Qualität 25 % und
    Bewertung 25 % auf die beiden Säulen verteilt: (0,25 * 70 + 0,25 * 70) / 0,5 = 70 -> Note B.
    Abdeckung (0,25 + 0,25) / (0,25 + 0,25) = 1."""
    erg = note.note(
        "x", "2026-10-19", _d(roic__wert="0.18", ev_ebit__aktuell="12"), GRUPPE, KARTE, SCORING, []
    )
    assert erg.saeulen["qualitaet"] == 70 and erg.saeulen["bewertung"] == 70
    assert erg.gesamt == 70 and erg.note == "B" and erg.abdeckung == 1


def test_missing_metric_reduces_coverage_and_caps() -> None:
    """Ohne EV/EBIT: nur Qualität 70, Abdeckung 0,25 / 0,5 = 0,5 < 0,7 -> Kappung auf 64 (C)."""
    erg = note.note(
        "x", "t", _d(roic__wert="0.18", ev_ebit__aktuell=None), GRUPPE, KARTE, SCORING, []
    )
    assert erg.abdeckung == Decimal("0.5") and erg.gesamt == 64 and erg.note == "C"
    assert "abdeckung_gering" in erg.kappungen


def test_caps_apply() -> None:
    eigen = _d(roic__wert="0.30", ev_ebit__aktuell="5")  # beste in beiden: je 90
    erg = note.note("x", "t", eigen, GRUPPE, KARTE, SCORING, ["altman_gefahr"])
    assert erg.gesamt == 64 and erg.note == "C"
    erg = note.note("x", "t", eigen, GRUPPE, KARTE, SCORING, ["stopp_flag"])
    assert erg.gesamt == 49 and erg.note == "D"


def test_konfidenz_levels() -> None:
    cfg = SCORING["konfidenz"]
    assert note.konfidenz(10, Decimal("0.95"), "large", True, True, cfg)[0] == "K1"
    assert note.konfidenz(6, Decimal("0.95"), "large", True, True, cfg)[0] == "K2"
    stufe, gruende = note.konfidenz(10, Decimal("0.95"), "micro", True, True, cfg)
    assert stufe == "K3" and any("Größenklasse micro" in g for g in gruende)
    assert note.konfidenz(2, Decimal("0.5"), "large", True, True, cfg)[0] == "K4"


def test_risk_class() -> None:
    """Volatilität 0,30 -> 3, Rückgang 0,20 -> 1, Verschuldung 2 -> 3, Größe large -> 2:
    Mittel 9 / 4 = 2,25 -> R2."""
    klasse, stufen = note.risiko(
        {
            "volatilitaet_3j": Decimal("0.30"),
            "drawdown_5j": Decimal("0.20"),
            "verschuldung_ebitda": Decimal("2"),
            "groesse": "large",
        },
        SCORING["risiko"],
    )
    assert stufen == {
        "volatilitaet_3j": 3,
        "drawdown_5j": 1,
        "verschuldung_ebitda": 3,
        "groesse": 2,
    }
    assert klasse == "R2"


def test_category_with_hysteresis() -> None:
    assert note.kategorie("B", "K1", False, True, [], False, 2)[0] == "Beobachten"
    assert note.kategorie("B", "K1", False, True, ["A"], False, 2)[0] == "Attraktiv"
    assert note.kategorie("A", "K3", False, True, ["A"], False, 2)[0] == "Beobachten"
    assert note.kategorie("C", "K1", False, None, [], True, 2)[0] == "Beobachten"
    assert note.kategorie("C", "K1", False, None, [], False, 2)[0] == "Neutral"
    assert note.kategorie("D", "K1", False, None, [], False, 2)[0] == "Unattraktiv"


def test_sectors_and_scorecards() -> None:
    assert sektoren.branche(3571, SECTORS).unter == "hardware"  # Apple
    assert sektoren.branche(2840, SECTORS).unter == "haushalt_koerperpflege"  # engster Bereich
    assert sektoren.scorecard(2840, False, SCORECARDS).id == "standard"
    assert sektoren.scorecard(6021, False, SCORECARDS).id == "banken"
    assert sektoren.scorecard(3571, True, SCORECARDS).id == "growth"
    assert sektoren.region("DE", SCORING["vergleichsgruppe"]["regionen"]) == "europa"
    assert note.groessenklasse(Decimal("3e12"), SCORING["groessenklassen"]) == "mega"
    assert note.groessenklasse(Decimal("1e8"), SCORING["groessenklassen"]) == "micro"


def test_peer_selection_by_revenue_and_multiples() -> None:
    """Umsatz 100: Kandidaten 50 und 200 gleich weit (|ln 0,5| = |ln 2|), Kennung entscheidet."""
    k = {"a": Decimal(200), "b": Decimal(50), "c": Decimal(1000), "d": Decimal(110)}
    assert vergleichsgruppe.naechste(Decimal(100), k, 3) == ["d", "a", "b"]
    r = Rechenweg("t", "1", "x", "t")
    gruppe = [{"pe": Decimal(v), "ev_ebit": None, "fcf_yield": None} for v in (10, 20, 30, 40, 50)]
    # KGV 20 gegen Median 30: Kurs relativ 30 / 20 = 1,5 -> Abschlag 1 - 1 / 1,5 = 0,333...
    abschlag = vergleichsgruppe.multiples_abschlag(r, {"pe": Decimal(20)}, gruppe)
    assert abschlag is not None and abschlag.quantize(Decimal("0.0001")) == Decimal("0.3333")


def test_market_risk_inputs() -> None:
    from datetime import date, timedelta

    tage = [
        marktrisiko.Tag(date(2020, 1, 1) + timedelta(days=i), Decimal(100 + (i % 2)), 1000)
        for i in range(800)
    ]
    vol = marktrisiko.volatilitaet(tage)
    assert vol is not None and Decimal("0.15") < vol < Decimal("0.17")  # ±1 % täglich
    assert marktrisiko.drawdown(tage) == Decimal(1) - Decimal(100) / Decimal(101)
    assert marktrisiko.in_eur(Decimal(25000), Decimal("0.874"), 100).quantize(
        Decimal("0.01")
    ) == Decimal("286.04")
