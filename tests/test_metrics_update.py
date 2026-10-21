"""Bauschritt 3: Kennzahlen aus der Datenbank (echte SEC-Testdaten) gegen die Handrechnungen.

Die Handrechnungen in tests/metrics/ nutzen von Hand aus den 10-K-Dokumenten abgelesene Werte.
Hier läuft derselbe Weg wie im Betrieb: Company Facts -> facts -> pit_query -> Reihen ->
Kennzahl. Stimmen beide überein, ist die Zuordnung der XBRL-Konzepte richtig.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from stockagent import kapitalmarkt_update, metrics_update, sec_update
from stockagent.cli import app
from stockagent.core import registry
from stockagent.data import inputs, store
from stockagent.paths import Paths
from tests.metrics.apple import APPLE, APPLE_10J, T25, q, rechne
from tests.sec_fixtures import AGENT, NOW, FakeWeb, no_sleep, project
from tests.test_kapitalmarkt import FakeWeb as KapitalmarktWeb

APPLE_ISIN = "US0378331005"
ISSUER = "sec:0000320193"
# Echte Schlusskurse von Yahoo (AAPL, USD, um Splits bereinigt), Rohdateien 6d1ecdd2bee4e25c...
# (Erstabruf) und a10ea11623e7f14b... (13.10.2026): letzter Handelstag vor jedem
# Geschäftsjahresende und der letzte Kurs vor NOW.
KURSE = {
    date(2019, 9, 27): "54.70500183105469",
    date(2020, 9, 25): "112.27999877929688",
    date(2021, 9, 24): "146.9199981689453",
    date(2022, 9, 23): "150.42999267578125",
    date(2023, 9, 29): "171.2100067138672",
    date(2024, 9, 27): "227.7899932861328",
    date(2025, 9, 26): "255.4600067138672",
    date(2026, 10, 13): "341.2699890136719",
}


# Echte Treasury-Zinsen 10 Yr (home.treasury.gov, Lauf vom 19.10.2026) an den Kurstagen oben
ZINSEN = {
    date(2019, 9, 27): "1.69",
    date(2020, 9, 25): "0.66",
    date(2021, 9, 24): "1.47",
    date(2022, 9, 23): "3.69",
    date(2023, 9, 29): "4.59",
    date(2024, 9, 27): "3.75",
    date(2025, 9, 26): "4.20",
    date(2026, 10, 13): "5.21",
}


def markt_laden(paths: Paths) -> None:
    """Zinsen wie oben, Damodaran aus tests/fixtures/damodaran/ (Apple als NasdaqGS:AAPL)."""
    kapitalmarkt_update.damodaran_update(paths, fetcher=KapitalmarktWeb(), now=NOW)
    conn = store.connect(paths.db)
    store.save_rates(
        conn,
        [(d, "rf_10y_USD", Decimal(v)) for d, v in ZINSEN.items()],
        "treasury",
        "0" * 64,
        NOW,
    )
    conn.close()


def kurse_laden(paths: Paths) -> None:
    conn = store.connect(paths.db)
    store.save_price_symbol(
        conn,
        store.PriceSymbol(
            APPLE_ISIN,
            "AAPL",
            "US",
            "openfigi",
            "zugeordnet",
            "Test",
            "Apple Inc.",
            "USD",
            "NasdaqGS",
            (),
            NOW,
            NOW,
        ),
    )
    rows = [
        store.PriceRow(APPLE_ISIN, d, Decimal(k), None, None, "USD", "AAPL", "yahoo")
        for d, k in KURSE.items()
    ]
    store.save_prices(conn, rows, [], "0" * 64, NOW)
    conn.close()


@pytest.fixture(scope="module")
def geladen(tmp_path_factory: pytest.TempPathFactory) -> Paths:
    mp = pytest.MonkeyPatch()
    mp.setenv("SEC_USER_AGENT", AGENT)
    paths = project(tmp_path_factory.mktemp("projekt"))
    sec_update.update(paths, isins=[APPLE_ISIN], fetcher=FakeWeb(), sleep=no_sleep, now=NOW)
    kurse_laden(paths)
    markt_laden(paths)
    metrics_update.update(paths, isins=[APPLE_ISIN], now=NOW)
    mp.undo()
    return paths


def _werte(paths: Paths, statistik: str = "wert") -> dict[str, store.MetricRow]:
    conn = store.connect(paths.db)
    rows = store.load_metrics(conn, ISSUER, statistik=statistik)
    conn.close()
    return {r.metric_id: r for r in rows if r.period_end == T25}


def test_database_matches_hand_calculation(geladen: Paths) -> None:
    db = _werte(geladen)
    assert set(db) == registry.ids()
    abweichend = {}
    # Die DCF-Szenarien nutzen die Historie von bis zu 10 Jahren, die Handrechnung in
    # tests/metrics/apple.py hat für Umlaufvermögen und Abschreibungen nur 2 bis 3 Jahre. Sie sind
    # in tests/metrics/test_dcf_szenarien.py von Hand geprüft und hier in
    # test_dcf_scenarios_ordered_and_repeatable.
    for metric_id, row in db.items():
        if metric_id.startswith("dcf_"):
            continue
        # Normalisiertes EV/EBIT braucht 10 Jahre EBIT (tests/metrics/apple.py APPLE_10J)
        hand = rechne(metric_id, APPLE_10J if metric_id == "ev_ebit_normalized" else APPLE)
        if hand.wert is None or row.value is None:
            if (hand.wert is None) != (row.value is None):
                abweichend[metric_id] = (hand.grund, row.grund)
            continue
        if q(hand.wert) != q(row.value):
            abweichend[metric_id] = (q(hand.wert), q(row.value))
    assert abweichend == {}


def test_trace_and_inputs_are_stored(geladen: Paths) -> None:
    row = _werte(geladen)["gross_margin"]
    trace = json.loads(row.calc_trace_json)
    assert trace["subjekt"] == ISSUER and trace["periode"] == "2025-09-27"
    assert [s["name"] for s in trace["schritte"]][-1] == "marge"
    eingaben = [v for s in trace["schritte"] for v in s["eingaben"].values() if isinstance(v, dict)]
    assert any("us-gaap:Revenue" in str(e["quelle"]) for e in eingaben)
    assert all(e["waehrung"] == "USD" for e in eingaben)


def test_trends_stored_for_latest_year(geladen: Paths) -> None:
    trends = {
        (r.metric_id, r.statistik): r
        for s in ("niveau", "cagr_5j", "steigung", "plausibilitaet")
        for r in _werte(geladen, s).values()
    }
    assert trends[("fcf", "niveau")].value == Decimal("98767000000")
    assert trends[("gross_margin", "steigung")].value is not None
    assert ("ebit_margin", "plausibilitaet") in trends


def test_run_is_point_in_time(geladen: Paths) -> None:
    """Datenstand vor dem 10-K 2025: letztes Geschäftsjahr ist 2024."""
    cfg = metrics_update.Konfiguration.laden(geladen.config)
    conn = store.connect(geladen.db)
    r = metrics_update.berechne(conn, ISSUER, datetime(2025, 6, 1, tzinfo=UTC), cfg)
    conn.close()
    assert r.stichtag is not None and r.stichtag.isoformat() == "2024-09-28"


def test_hinweise_saved(geladen: Paths) -> None:
    conn = store.connect(geladen.db)
    h = store.load_hinweise(conn, ISSUER)
    run = store.load_metric_run(conn, ISSUER)
    conn.close()
    assert run is not None and run[3] == "1.4"
    # Apple 2025: Piotroski 8, Altman Z'' 2,31, Beneish -2,23, Sloan 0,1 %: keine Schwellenregel
    assert not [x for x in h if x.regel in ("H-01", "H-02", "H-03", "H-04")]
    assert all(x.status == "offen" and x.an_agent for x in h)


def test_cli_metrics_show(geladen: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKAGENT_HOME", str(geladen.root))
    out = CliRunner().invoke(app, ["metrics", "show", APPLE_ISIN])
    assert out.exit_code == 0, out.output
    assert "Bruttomarge" in out.output and "46,9 %" in out.output
    out = CliRunner().invoke(app, ["metrics", "show", APPLE_ISIN, "--rechenweg", "gross_margin"])
    assert out.exit_code == 0, out.output
    assert "marge = zaehler / nenner" in out.output and "CP-02 ok" in out.output


def test_unknown_isin(tmp_path: Path) -> None:
    paths = project(tmp_path)
    (res,) = metrics_update.update(paths, isins=["US0000000000"], now=NOW)
    assert res.fehler == "keinem SEC-Melder zugeordnet"


def test_prior_years_store_value_without_trace(geladen: Paths) -> None:
    conn = store.connect(geladen.db)
    rows = store.load_metrics(conn, ISSUER, metric_id="gross_margin", statistik="wert")
    conn.close()
    vorjahre = [r for r in rows if r.period_end != T25]
    assert vorjahre and all(r.calc_trace_json is None for r in vorjahre)
    assert any(r.value is not None for r in vorjahre)


def test_prior_year_trace_recomputed_on_demand(
    geladen: Paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = store.connect(geladen.db)
    (gespeichert,) = [
        r
        for r in store.load_metrics(conn, ISSUER, metric_id="gross_margin", statistik="wert")
        if r.period_end.year == 2024
    ]
    run = store.load_metric_run(conn, ISSUER)
    assert run is not None
    cfg = metrics_update.Konfiguration.laden(geladen.config)
    erg = metrics_update.nachrechnen(
        conn, ISSUER, run[1].replace(tzinfo=UTC), "gross_margin", 2024, cfg
    )
    conn.close()
    assert erg is not None and erg.wert == gespeichert.value  # bitgleich (CP-08)
    monkeypatch.setenv("STOCKAGENT_HOME", str(geladen.root))
    out = CliRunner().invoke(
        app, ["metrics", "show", APPLE_ISIN, "--rechenweg", "gross_margin", "--jahr", "2024"]
    )
    assert out.exit_code == 0, out.output
    assert "Nachgerechnet" in out.output and "2024-09-28" in out.output


def test_trend_trace_recomputed_on_demand(geladen: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    conn = store.connect(geladen.db)
    (gespeichert,) = store.load_metrics(conn, ISSUER, metric_id="fcf", statistik="steigung")
    conn.close()
    assert gespeichert.calc_trace_json is None and gespeichert.value is not None
    monkeypatch.setenv("STOCKAGENT_HOME", str(geladen.root))
    out = CliRunner().invoke(
        app, ["metrics", "show", APPLE_ISIN, "--rechenweg", "fcf", "--trend", "steigung"]
    )
    assert out.exit_code == 0, out.output
    assert f"= {gespeichert.value}" in out.output.replace("\n", " ")


def test_current_valuation_uses_latest_close(geladen: Paths) -> None:
    """KGV aktuell: 341,2699890136719 / 7,46 = 45,7466 (Kurs 13.10.2026, Gewinn je Aktie 2025)."""
    aktuell = _werte(geladen, "aktuell")
    cfg = metrics_update.Konfiguration.laden(geladen.config)
    assert set(aktuell) == {d["id"] for d in cfg.metrics["metrics"] if d.get("kurs")}
    assert q(aktuell["pe"].value, 4) == Decimal("45.7466")
    trace = json.loads(aktuell["pe"].calc_trace_json)
    assert "2026-10-13" in json.dumps(trace)


def test_percentile_against_own_history(geladen: Paths) -> None:
    """KGV je Geschäftsjahr 2020 bis 2025 aus den Kursen oben und dem Gewinn je Aktie; das
    aktuelle KGV 45,7 liegt über allen: Anteil der Jahre mit höchstens so hohem KGV = 1."""
    p = _werte(geladen, "perzentil_historie")
    assert p["pe"].value == 1
    assert set(p) == {
        "pe",
        "ev_ebit",
        "ev_sales",
        "fcf_yield",
        "pb",
        "dividend_yield",
        "ev_ebit_normalized",
    }


def test_cli_shows_valuation(geladen: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKAGENT_HOME", str(geladen.root))
    out = CliRunner().invoke(app, ["metrics", "show", APPLE_ISIN])
    assert out.exit_code == 0, out.output
    assert "Bewertung mit Börsenkurs" in out.output and "13.10.2026" in out.output
    out = CliRunner().invoke(app, ["metrics", "show", APPLE_ISIN, "-r", "pe", "--aktuell"])
    assert out.exit_code == 0, out.output
    assert "Yahoo AAPL Schlusskurs 2026-10-13" in out.output


def test_dividend_events_per_fiscal_year(geladen: Paths) -> None:
    """Echte Dividenden von Apple bei Yahoo im Geschäftsjahr 2025 (29.09.2024 bis 27.09.2025):
    08.11.2024, 10.02.2025, 12.05.2025, 11.08.2025 (Rohdatei 6d1ecdd2bee4e25c...)."""
    conn = store.connect(geladen.db)
    events = [
        store.PriceEvent(APPLE_ISIN, d, "dividende", Decimal(v), None, None, "USD", "AAPL", "yahoo")
        for d, v in [
            (date(2024, 11, 8), "0.25"),
            (date(2025, 2, 10), "0.25"),
            (date(2025, 5, 12), "0.26"),
            (date(2025, 8, 11), "0.26"),
            (date(2025, 11, 10), "0.26"),  # schon Geschäftsjahr 2026
        ]
    ]
    store.save_prices(conn, [], events, "0" * 64, NOW)
    stichtage = [T25, date(2024, 9, 28), date(2023, 9, 30), date(2018, 9, 29)]
    je_jahr = inputs.dividenden_yahoo(conn, APPLE_ISIN, stichtage)
    conn.close()
    assert je_jahr[T25].wert == 4 and "2025-08-11" in je_jahr[T25].quelle
    # 2024: Kurse decken das Jahr ab, Dividenden davor nicht gespeichert -> 0
    assert je_jahr[date(2024, 9, 28)].wert == 0
    # Der Zeitraum bis 30.09.2023 beginnt vor dem ersten gespeicherten Kurs (27.09.2019): keine
    # Aussage, also auch keine 0
    assert date(2023, 9, 30) not in je_jahr


def test_dcf_scenarios_ordered_and_repeatable(geladen: Paths) -> None:
    db = _werte(geladen)
    assert db["dcf_bear"].value < db["dcf_base"].value < db["dcf_bull"].value
    conn = store.connect(geladen.db)
    run = store.load_metric_run(conn, ISSUER)
    assert run is not None
    cfg = metrics_update.Konfiguration.laden(geladen.config)
    erg = metrics_update.nachrechnen(
        conn, ISSUER, run[1].replace(tzinfo=UTC), "dcf_base", 2025, cfg
    )
    conn.close()
    assert erg is not None and erg.wert == db["dcf_base"].value  # CP-08


def test_ttm_valuation_from_quarterly_reports(geladen: Paths) -> None:
    """Gewinn je Aktie TTM bis 27.06.2026: 7,46 (GJ 2025) + 6,88 (9 Monate 2026) - 5,62
    (9 Monate 2025) = 8,72 (10-Q Accession 0000320193-26-000020). KGV TTM mit dem Kurs vom
    13.10.2026: 341,2699890136719 / 8,72 = 39,1365."""
    ttm = _werte(geladen, "ttm")
    assert q(ttm["pe"].value, 4) == Decimal("39.1365")
    trace = json.loads(ttm["pe"].calc_trace_json)
    assert trace["periode"] == "2026-06-27"
    assert "ebit_margin" in ttm and "shareholder_yield" not in ttm
