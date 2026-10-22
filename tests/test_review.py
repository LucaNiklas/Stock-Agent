"""Korrekturen aus dem Review vom 22.10.2026 (Befunde 1 bis 10, Methodik 5.8)."""

from __future__ import annotations

import http.client
import io
import json
import re
import shutil
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from stockagent import bewertung, eskalationen, orchestrator
from stockagent.core import note, vergleichsgruppe
from stockagent.core.calc import Eingabe, Rechenweg
from stockagent.core.marktkennzahlen import boersenwert
from stockagent.core.reihen import Reihen
from stockagent.dashboard import build
from stockagent.data import http as sa_http
from stockagent.data import store
from stockagent.gates import number, wording
from stockagent.paths import Paths
from stockagent.titelliste import Daten
from tests.sec_fixtures import ROOT, _listing
from tests.test_bewertung import FIRMEN, NOW, Attrappe, _seed


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    shutil.copytree(ROOT / "config", tmp_path / "config")
    (tmp_path / "docs").mkdir()
    shutil.copy(ROOT / "docs/METHODOLOGY_CHANGELOG.md", tmp_path / "docs")
    p = Paths(tmp_path)
    _seed(p)
    return p


# ------------------------------------------------------------------ Befund 1: Zuordnung


def test_rating_maps_all_us_stocks_first_on_fresh_install(paths: Paths) -> None:
    """20 von 30 US-Aktien zugeordnet, 10 nie abgefragt (33 % > 10 %): erst alle zuordnen."""
    conn = store.connect(paths.db)
    try:
        neu = [_listing(f"US99999{i:05d}", f"NEU {i}", None, None) for i in range(10)]
        alle = [*conn.execute("SELECT isin FROM listings").fetchall()]
        assert len(alle) == 20
        conn.executemany(
            "INSERT INTO listings (isin, name, isin_country, on_xetra, country, country_source, "
            "is_receipt, isin_valid, listed, first_seen, last_seen, snapshot_id) "
            "VALUES (?, ?, 'US', true, 'US', 'isin', false, true, true, current_date, "
            "current_date, 1)",
            [(x.isin, x.name) for x in neu],
        )
        assert store.us_zuordnung_stand(conn) == (30, 10)
    finally:
        conn.close()
    a = Attrappe()
    bewertung.bewerten(paths, FIRMEN[-1][0], lader=a.lader(), now=NOW)
    assert "zuordnung" in a.abrufe
    assert not vergleichsgruppe.zuordnung_ausreichend(30, 10, Decimal("0.1"))
    assert vergleichsgruppe.zuordnung_ausreichend(30, 2, Decimal("0.1"))


# ------------------------------------------------------------------ Befund 2: Netz


def test_fetch_retries_incomplete_read_and_dns_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    fehler: list[Exception] = [
        http.client.IncompleteRead(b"x", 10),
        ConnectionResetError("Remote end closed connection"),
    ]

    class Antwort(io.BytesIO):
        def __enter__(self) -> Antwort:
            return self

        def __exit__(self, *a: object) -> None:
            pass

    def urlopen(req: Any, timeout: float) -> Antwort:
        if fehler:
            raise fehler.pop(0)
        return Antwort(b"ok")

    monkeypatch.setattr(sa_http.urllib.request, "urlopen", urlopen)
    pausen: list[float] = []
    assert sa_http.fetch("https://x", "ua", sleep=pausen.append) == b"ok"
    assert pausen == [2, 4]


# ------------------------------------------------------------------ Befund 3: Tiefenanalyse


def test_deep_analysis_result_caps_category() -> None:
    esk = {"kategorie": "Eskaliert", "run_id": "r"}
    assert eskalationen.begrenzt("Attraktiv", esk) == "Eskaliert"
    assert eskalationen.begrenzt("Unattraktiv", esk) == "Unattraktiv"
    beob = {"kategorie": "Beobachten", "run_id": "r"}
    assert eskalationen.begrenzt("Attraktiv", beob) == "Beobachten"
    assert eskalationen.begrenzt("Neutral", beob) == "Neutral"  # nie eine Aufwertung (HR-13)
    assert eskalationen.begrenzt("Attraktiv", None) == "Attraktiv"


def _lauf(paths: Paths, run_id: str, isin: str, status: str, erstellt: datetime) -> None:
    z = orchestrator.Zustand(
        run_id=run_id,
        isin=isin,
        issuer_id="sec:1",
        cik="1",
        name="X",
        erstellt=erstellt.isoformat(timespec="seconds"),
        config_hash=orchestrator.config_hash(paths),
        status=status,
    )
    (paths.runs / run_id).mkdir(parents=True)
    orchestrator._speichern(paths, z)


def test_list_shows_escalated_deep_analysis(paths: Paths) -> None:
    isin = FIRMEN[-1][0]
    bewertung.bewerten(paths, isin, lader=Attrappe().lader(), now=NOW)
    run_id = f"2026-10-20T10-00-00Z_{isin}"
    _lauf(paths, run_id, isin, "eskaliert", NOW)
    (paths.runs / run_id / "decision.json").write_text(json.dumps({"kategorie": "Eskaliert"}))
    zeile = next(z for z in Daten(paths).zeilen if z.isin == isin)
    assert zeile.kategorie == "Eskaliert" and run_id in zeile.tiefenanalyse
    assert {h["kategorie"] for h in zeile.horizonte.values()} == {"Eskaliert"}


# ------------------------------------------------------------------ Befund 4: alte Läufe


def test_stale_deep_analyses_do_not_block_new_ones(paths: Paths) -> None:
    alt = datetime.now(UTC) - timedelta(hours=5)
    for i in range(3):
        _lauf(paths, f"2026-10-20T0{i}-00-00Z_US000000000{i}", f"US000000000{i}", "laeuft", alt)
    frisch = datetime.now(UTC)
    _lauf(paths, "2026-10-22T09-00-00Z_US0000000099", "US0000000099", "laeuft", frisch)
    aktiv = orchestrator.aufraeumen(paths)
    assert [z.isin for z in aktiv] == ["US0000000099"]
    stati = {z.isin: z.status for z in orchestrator.laufende(paths)}
    assert list(stati.values()).count("abgebrochen") == 3


# ------------------------------------------------------------------ Befund 5: Aktienzahl


def _reihen(**werte: Eingabe) -> Reihen:
    t = date(2025, 9, 27)
    return Reihen("x", (t,), {k: {t: v} for k, v in werte.items()})


def _e(wert: str, einheit: str = "shares", waehrung: str | None = None) -> Eingabe:
    return Eingabe(Decimal(wert), "test", einheit, date(2025, 9, 27), waehrung)


def test_current_market_cap_uses_cover_page_shares() -> None:
    """Kurs 200, Durchschnitt 1000 Aktien, Deckblatt 900 + 50 (zwei Gattungen) = 950:
    Börsenwert 200 * 950 = 190000. Unplausible 2000 (200 % des Durchschnitts): 200 * 1000."""
    t = date(2025, 9, 27)
    basis = {"kurs": _e("200", "per_share", "USD"), "shares_diluted": _e("1000")}
    d = _reihen(**basis, aktien_aktuell_1=_e("900"), aktien_aktuell_2=_e("50"))
    r = Rechenweg("t", "1", "", "")
    assert boersenwert(r, d, t) == Decimal("190000")
    d = _reihen(**basis, aktien_aktuell_1=_e("2000"))
    r = Rechenweg("t", "1", "", "")
    assert boersenwert(r, d, t) == Decimal("200000")
    assert any(not p.bestanden and p.cp_id == "CP-05" for p in r.pruefungen)
    assert boersenwert(Rechenweg("t", "1", "", ""), _reihen(**basis), t) == Decimal("200000")


# ------------------------------------------------------------------ Befund 6


def test_hyperinflation_caps_confidence_and_config_is_valid() -> None:
    assert note.konfidenz_hoechstens("K1", "K3", "Türkei")[0] == "K3"
    assert note.konfidenz_hoechstens("K4", "K3", "Türkei") == ("K4", None)
    cfg = yaml.safe_load((ROOT / "config/hyperinflation.yaml").read_text())
    for iso, e in cfg["laender"].items():
        assert re.fullmatch(r"[A-Z]{2}", iso) and date.fromisoformat(e["ab"])
    q = yaml.safe_load((ROOT / "config/withholding_tax.yaml").read_text())
    for iso, e in q["laender"].items():
        assert re.fullmatch(r"[A-Z]{2}", iso)
        assert 0 <= Decimal(e["anrechenbar"]) <= Decimal(e["satz"]) < 1


def test_static_dashboard_for_reading_mode(paths: Paths, tmp_path: Path) -> None:
    bewertung.bewerten(paths, FIRMEN[-1][0], lader=Attrappe().lader(), now=NOW)
    ziel = build.bauen(paths, tmp_path / "lesemodus.html")
    html = ziel.read_text()
    m = re.search(r"window\.LESEMODUS=(.*?);</script>", html, re.S)
    assert m is not None
    daten = json.loads(m.group(1).replace("<\\/", "</"))
    assert len(daten["zeilen"]) == 20 and FIRMEN[-1][0] in daten["titel"]
    assert "/api/methodik" in daten["fest"] and "lokal(p,o)" in html


# ------------------------------------------------------------------ Befund 7: ESEF als Vergleich


def test_esef_issuers_are_peer_candidates(paths: Paths) -> None:
    conn = store.connect(paths.db)
    try:
        conn.execute(
            "INSERT INTO listings (isin, name, isin_country, on_xetra, country, country_source, "
            "is_receipt, isin_valid, listed, first_seen, last_seen, snapshot_id, lei) "
            "VALUES ('NL0000000001', 'EURO NV', 'NL', true, 'NL', 'gleif', false, true, true, "
            "current_date, current_date, 1, '724500ABCDEF12345678')"
        )
        conn.execute(
            "INSERT INTO metric_runs VALUES ('metrics:lei:x', 'lei:724500ABCDEF12345678', ?, "
            "NULL, '1.8', ?)",
            [NOW.replace(tzinfo=None), NOW.replace(tzinfo=None)],
        )
        titel = {t.issuer_id: t for t in bewertung._titel(conn)}
    finally:
        conn.close()
    esef = titel["lei:724500ABCDEF12345678"]
    assert esef.isin == "NL0000000001" and esef.land == "NL" and esef.sic is None


# ------------------------------------------------------------------ Befund 8: Zinsdeckung


def test_interest_cover_threshold_per_scorecard(paths: Paths) -> None:
    cfg = bewertung.Konfig.laden(paths.config)
    werte = {("interest_coverage", "wert"): Decimal("1.8")}
    conn = store.connect(paths.db)
    try:
        standard = bewertung._alle_kappungen(conn, "sec:x", werte, cfg.metrics, cfg.scoring)
        versorger = bewertung._alle_kappungen(
            conn,
            "sec:x",
            werte,
            cfg.metrics,
            {
                **cfg.scoring,
                "stopp_zinsdeckung_unter": cfg.scorecards["scorecards"]["versorger"][
                    "stopp_zinsdeckung_unter"
                ],
            },
        )
    finally:
        conn.close()
    assert standard[1] is True and versorger[1] is False


# ------------------------------------------------------------------ Befund 9 und 10


def test_momentum_pillar_without_fundamentals() -> None:
    h = yaml.safe_load((ROOT / "config/horizonte.yaml").read_text())
    ids = {k["kennzahl"] for k in h["momentum"]["kennzahlen"]}
    assert ids.isdisjoint({"revenue_growth", "ebit_margin"})


@pytest.mark.parametrize(
    ("text", "verstoss"),
    [
        ("Der Umsatz stieg um drei Prozent.", True),
        ("Der Gewinn hat sich verdoppelt.", True),
        ("Rund zwanzig Milliarden Dollar Schulden.", True),
        ("Die Marge halbierte sich.", True),
        ("Das Unternehmen hat zwei Segmente.", False),
        ("{{revenue@FY2025}} stieg stärker als {{ebit@FY2025}}.", False),
    ],
)
def test_number_gate_catches_numbers_in_words(text: str, verstoss: bool) -> None:
    assert bool(number.offending(text)) is verstoss


@pytest.mark.parametrize(
    ("text", "verstoss"),
    [
        ("Eine gute Einstiegschance.", True),
        ("Anleger sollten jetzt kaufen.", True),
        ("Es lohnt sich ein Kauf.", True),
        ("Das Kurspotenzial ist hoch.", True),
        ("Wir würden übergewichten.", True),
        ("Die Bewertung ist hoch, die Risiken bleiben.", False),
    ],
)
def test_wording_gate_catches_more_recommendations(text: str, verstoss: bool) -> None:
    assert bool(wording.offending(text)) is verstoss
