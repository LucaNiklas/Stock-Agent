"""Bauschritt 5: Bewerten auf Anfrage, Tiers und Dashboard ohne Netz.

20 erfundene Firmen derselben Unterbranche (SIC 3571, Region Nordamerika) mit fertigen
Kennzahlen in der Datenbank. Die Netzabrufe laufen über Attrappen (`Lader`).
"""

from __future__ import annotations

import json
import shutil
import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from http.client import HTTPConnection
from pathlib import Path

import pytest
import yaml

from stockagent import bewertung, tiers
from stockagent.dashboard import app as dashboard
from stockagent.data import store
from stockagent.data.sources import sec
from stockagent.paths import Paths
from tests.sec_fixtures import ROOT, _listing

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
STICHTAG = date(2025, 12, 31)


def _isin(stamm: str) -> str:
    """Gültige US-ISIN mit Prüfziffer aus neun Zeichen."""
    rumpf = "US" + stamm
    ziffern = "".join(str(int(c, 36)) for c in rumpf)
    summe = 0
    for i, c in enumerate(reversed(ziffern)):
        d = int(c) * (2 if i % 2 == 0 else 1)
        summe += d - 9 if d > 9 else d
    return rumpf + str((10 - summe % 10) % 10)


FIRMEN = [(_isin(f"00000{i:04d}"), f"{i:010d}") for i in range(1, 21)]


HOCH = [
    ("gp_to_assets", "wert"),
    ("roic", "wert"),
    ("fcf_margin", "wert"),
    ("piotroski_f_score", "wert"),
    ("fcf_yield", "aktuell"),
    ("margin_of_safety", "aktuell"),
    ("interest_coverage", "wert"),
    ("altman_z_double_prime", "wert"),
    ("revenue_cagr_5y", "wert"),
    ("fcf_per_share_cagr_5y", "wert"),
    ("ebit_margin", "steigung"),
    ("fcf_margin", "steigung"),
    ("shareholder_yield", "aktuell"),
]
NIEDRIG = [
    ("ebit_margin", "stdabw"),
    ("ev_ebit", "aktuell"),
    ("growth_gap", "aktuell"),
    ("net_debt_to_ebitda", "wert"),
    ("debt_maturity_12m", "wert"),
    ("share_count_change_3y", "wert"),
    ("acquisition_intensity", "wert"),
]


def _metriken(i: int) -> dict[tuple[str, str], str]:
    """Firma i: höhere Nummer ist in jeder Kennzahl der Scorecard besser, ohne Gleichstand.
    Die Werte sind erfunden, nur ihre Reihenfolge zählt."""
    out = {k: f"{i / 100}" for k in HOCH} | {k: f"{(21 - i) / 100}" for k in NIEDRIG}
    out[("growth_gap", "aktuell")] = f"{(10 - i) / 100}"
    # Über den Schwellen der Kappungen (Zinsdeckung 2, Altman-Gefahrenzone 1,1)
    out[("interest_coverage", "wert")] = str(2 + i)
    out[("altman_z_double_prime", "wert")] = str(2 + i)
    out[("ebit_margin", "wert")] = "0.2"
    out[("revenue_cagr_3y", "wert")] = "0.05"
    out[("market_cap", "aktuell")] = str(10**9 * (20 + i))
    return out


VERSION = str(
    yaml.safe_load((ROOT / "config" / "metrics.yaml").read_text("utf-8"))["methodology_version"]
)


def _naiv(t: datetime) -> datetime:
    return t.replace(tzinfo=None)


def _seed(paths: Paths, *, computed: datetime = NOW) -> None:
    conn = store.connect(paths.db)
    try:
        rows = [_listing(isin, f"FIRMA {n} INC.", None, None) for n, (isin, _) in enumerate(FIRMEN)]
        store.apply_snapshot(
            conn, rows, retrieved_at=NOW, source_as_of=NOW.date(), raw=[], forced=False
        )
        store.save_isin_cik(
            conn,
            [store.IsinCik(isin, cik, None, "test", "zugeordnet", "") for isin, cik in FIRMEN],
            NOW,
        )
        for n, (_isin, cik) in enumerate(FIRMEN, start=1):
            iid = sec.issuer_id(cik)
            store.save_issuer(
                conn,
                store.IssuerRow(
                    iid,
                    None,
                    cik,
                    f"FIRMA {n}",
                    "US",
                    "3571",
                    "",
                    "1231",
                    None,
                    None,
                    None,
                    None,
                    None,
                    "test",
                    "x",
                    NOW,
                ),
            )
            run = f"metrics:{iid}:t"
            conn.execute(
                "INSERT INTO metric_runs VALUES (?, ?, ?, ?, ?, ?)",
                [run, iid, _naiv(NOW), STICHTAG, VERSION, _naiv(computed)],
            )
            conn.executemany(
                "INSERT INTO metrics VALUES "
                "(?, ?, ?, '1', ?, ?, ?, NULL, NULL, '[]', '[]', NULL, ?)",
                [[run, iid, k, s, STICHTAG, v, _naiv(NOW)] for (k, s), v in _metriken(n).items()],
            )
    finally:
        conn.close()


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    shutil.copytree(ROOT / "config", tmp_path / "config")
    p = Paths(tmp_path)
    _seed(p)
    return p


class Attrappe:
    """Zählt die Netzabrufe, lädt nichts außer dem Umsatz aller Melder."""

    def __init__(self) -> None:
        self.abrufe: list[str] = []

    def lader(self) -> bewertung.Lader:
        def umsatz(p: Paths, zeitraum: str, konzepte: list[str]) -> None:
            self.abrufe.append(f"umsatz {zeitraum}")
            conn = store.connect(p.db)
            try:
                store.save_revenue_frame(
                    conn,
                    zeitraum,
                    konzepte[0],
                    [
                        (cik, Decimal(10**9 * n), None, STICHTAG, "acc")
                        for n, (_, cik) in enumerate(FIRMEN, start=1)
                    ],
                    "sha",
                    NOW,
                )
            finally:
                conn.close()

        return bewertung.Lader(
            sec=lambda p, i: self.abrufe.append(f"sec {len(i)}"),
            kurse=lambda p, i: self.abrufe.append(f"kurse {len(i)}"),
            markt=lambda p: None,
            wechselkurse=lambda p: None,
            kennzahlen=lambda p, i: self.abrufe.append(f"kennzahlen {len(i)}"),
            umsatz=umsatz,
            esef=lambda p, i: self.abrufe.append(f"esef {len(i)}"),
            insider=lambda p, i: None,  # Insider prüft tests/test_insider.py
        )


def test_rating_against_peer_group(paths: Paths) -> None:
    """Firma 20 ist in allen Kennzahlen die beste der 20: jede Kennzahl Perzentil
    (19 + 0,5) / 20 * 100 = 97,5, Gesamtwert 97,5, Note A. Ohne Vorlauf Kategorie Beobachten
    (Hysterese: zwei Läufe nacheinander A oder B)."""
    a = Attrappe()
    isin = FIRMEN[-1][0]
    erg = bewertung.bewerten(paths, isin, lader=a.lader(), now=NOW)
    assert erg.note == "A", erg.grund
    assert erg.stufe == "Unterbranche in der Region" and len(erg.gruppe) == 19
    assert a.abrufe == ["umsatz CY2025"]  # alles frisch, nichts nachgeladen
    g = erg.grade
    assert g is not None and g.score == Decimal("97.5")
    assert g.kategorie == "Beobachten"
    detail = json.loads(g.detail_json or "{}")
    assert detail["bewertungsbedingung"]["erfuellt"] is True  # growth_gap -0,10 < 0
    assert detail["saeulen"]["insider"] is None

    # Zweiter Lauf am Folgetag: die Hysterese ist erfüllt, es bleibt die Konfidenz (die
    # Testfirmen haben keine Jahre-Historie, also K4) als Grund für Beobachten.
    erg2 = bewertung.bewerten(paths, isin, lader=a.lader(), now=NOW + timedelta(days=1))
    assert erg2.grade is not None and erg2.grade.konfidenz == "K4"
    grund = json.loads(erg2.grade.detail_json or "{}")["kategorie_grund"]
    assert grund == "Note A, aber Konfidenz K4"
    conn = store.connect(paths.db)
    try:
        assert [n for _, n in store.snapshot_grades(conn, isin)] == ["A", "A"]
    finally:
        conn.close()


def test_worst_firm_gets_low_grade(paths: Paths) -> None:
    """Firma 1 ist überall die schlechteste: Perzentil 0,5 / 20 * 100 = 2,5 -> Note E."""
    erg = bewertung.bewerten(paths, FIRMEN[0][0], lader=Attrappe().lader(), now=NOW)
    assert erg.note == "E" and erg.grade is not None
    assert erg.grade.score == Decimal("2.5") and erg.grade.kategorie == "Unattraktiv"


def test_stale_peers_are_reloaded(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "config", tmp_path / "config")
    p = Paths(tmp_path)
    _seed(p, computed=NOW - timedelta(days=30))
    a = Attrappe()
    bewertung.bewerten(p, FIRMEN[5][0], lader=a.lader(), now=NOW)
    assert a.abrufe[:4] == ["sec 1", "kurse 1", "kennzahlen 1", "umsatz CY2025"]
    assert a.abrufe[4:] == ["sec 1", "kurse 1", "kennzahlen 1"] * 19  # je Titel einzeln


def test_old_methodology_version_is_reloaded(paths: Paths) -> None:
    """Kennzahlen von heute, aber mit einer älteren Methodik-Version (JPMorgan am 21.10.2026:
    Lauf vor Schritt 8 ohne Bankkennzahlen, Abdeckung 36 %): eigene Daten neu laden."""
    isin, cik = FIRMEN[-1]
    conn = store.connect(paths.db)
    try:
        conn.execute(
            "UPDATE metric_runs SET methodology_version = '1.6' WHERE issuer_id = ?",
            [sec.issuer_id(cik)],
        )
    finally:
        conn.close()
    a = Attrappe()
    bewertung.bewerten(paths, isin, lader=a.lader(), now=NOW)
    assert a.abrufe[:3] == ["sec 1", "kurse 1", "kennzahlen 1"]


def test_too_small_group_and_other_scorecard(paths: Paths) -> None:
    conn = store.connect(paths.db)
    try:
        conn.execute("UPDATE issuers SET sector_sic = '6021' WHERE cik = ?", [FIRMEN[0][1]])
    finally:
        conn.close()
    # Seit Schritt 8 eigene Scorecard: ohne andere Banken ist die Vergleichsgruppe leer
    bank = bewertung.bewerten(paths, FIRMEN[0][0], lader=Attrappe().lader(), now=NOW)
    assert bank.note == "N" and "Vergleichsgruppe zu klein (0" in (bank.grund or "")
    # Holding: at-equity-Beteiligungen über 50 % der Bilanzsumme -> N mit Grund
    conn = store.connect(paths.db)
    try:
        iid = sec.issuer_id(FIRMEN[2][1])
        conn.execute(
            "INSERT INTO metrics SELECT run_id, issuer_id, 'holding_share', metric_version, "
            "statistik, period_end, '0.6', NULL, NULL, warnungen_json, vermerke_json, NULL, "
            "computed_at FROM metrics WHERE issuer_id = ? AND metric_id = 'ebit_margin' "
            "AND statistik = 'wert'",
            [iid],
        )
    finally:
        conn.close()
    holding = bewertung.bewerten(paths, FIRMEN[2][0], lader=Attrappe().lader(), now=NOW)
    assert holding.note == "N" and "Summe der Teile" in (holding.grund or "")
    conn = store.connect(paths.db)
    try:
        conn.execute("DELETE FROM metrics WHERE issuer_id <> ?", [sec.issuer_id(FIRMEN[1][1])])
    finally:
        conn.close()
    allein = bewertung.bewerten(paths, FIRMEN[1][0], lader=Attrappe().lader(), now=NOW)
    assert allein.note == "N" and "zu klein" in (allein.grund or "")


def test_unknown_isin_is_status_n(paths: Paths) -> None:
    erg = bewertung.bewerten(paths, "DE0007164600", lader=Attrappe().lader(), now=NOW)
    assert erg.note == "N" and "weder SEC-Melder noch ESEF" in (erg.grund or "")


# ------------------------------------------------------------------ Tiers


def test_tier_import_and_level(paths: Paths, tmp_path: Path) -> None:
    datei = tmp_path / "sp500.csv"
    datei.write_text(
        "Fondsname,Beispiel\nStand,19.10.2026\n\nTicker,Name,ISIN\n"
        f"A,Firma 1,{FIRMEN[0][0]}\nB,Firma 2,{FIRMEN[1][0]}\nX,Ungültig,US0000000001\n",
        "utf-8",
    )
    erg = tiers.importieren(paths, "sp500", datei, date(2026, 10, 19))
    assert (erg.mitglieder, erg.neu, erg.raus) == (2, 2, 0)
    stufen = tiers.stufen_aller(paths)
    assert stufen[FIRMEN[0][0]] == (1, ["sp500"]) and stufen[FIRMEN[5][0]] == (4, [])

    # Neuer Stand ohne Firma 2: sie scheidet aus, alter Stand bleibt für Backtests
    datei.write_text(f"ISIN;Name\n{FIRMEN[0][0]};Firma 1\n", "utf-8")
    erg = tiers.importieren(paths, "sp500", datei, date(2026, 11, 1))
    assert (erg.neu, erg.raus) == (0, 1)
    conn = store.connect(paths.db)
    try:
        assert FIRMEN[1][0] in store.index_memberships(conn, date(2026, 10, 20))
        assert FIRMEN[1][0] not in store.index_memberships(conn)
    finally:
        conn.close()
    # Ein Länderindex zählt nur im eigenen Land
    cfg = tiers.konfig(paths)
    assert tiers.stufe("DE", ["sp500"], cfg) == (4, [])
    assert tiers.stufe("DE", ["eurostoxx50", "dax"], cfg)[0] == 1


# ------------------------------------------------------------------ Dashboard


@pytest.fixture
def server(paths: Paths):  # type: ignore[no-untyped-def]
    bewertung.bewerten(paths, FIRMEN[-1][0], lader=Attrappe().lader(), now=NOW)
    srv = dashboard.server(paths, 0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def _anfrage(
    srv, methode: str, pfad: str, kopf: dict[str, str] | None = None, body: bytes | None = None
) -> tuple[int, bytes]:  # type: ignore[no-untyped-def]
    c = HTTPConnection("127.0.0.1", srv.server_address[1])
    c.request(methode, pfad, body=body, headers=kopf or {})
    r = c.getresponse()
    return r.status, r.read()


def test_dashboard_list_filters_and_detail(server) -> None:  # type: ignore[no-untyped-def]
    status, body = _anfrage(server, "GET", "/")
    assert status == 200 and b"Stockagent" in body
    d = json.loads(_anfrage(server, "GET", "/api/liste")[1])
    assert d["gesamt"] == 20 and d["bewertet"] == 1
    assert dict(d["facetten"]["note"])["A"] == 1
    d = json.loads(_anfrage(server, "GET", "/api/liste?note=A")[1])
    assert [z["isin"] for z in d["zeilen"]] == [FIRMEN[-1][0]]
    d = json.loads(_anfrage(server, "GET", "/api/liste?q=firma%201")[1])
    assert d["anzahl"] == 11  # FIRMA 1 und FIRMA 10 bis 19 (Name enthält "firma 1")
    t = json.loads(_anfrage(server, "GET", f"/api/titel/{FIRMEN[-1][0]}")[1])
    assert t["note"]["grade"] == "A" and t["detail"]["gruppe_stufe"] == "Unterbranche in der Region"
    csv = _anfrage(server, "GET", "/api/export.csv?note=A")[1].decode()
    assert csv.splitlines()[0].startswith("isin;name") and len(csv.splitlines()) == 2


def test_dashboard_rejects_foreign_host_and_origin(server) -> None:  # type: ignore[no-untyped-def]
    assert _anfrage(server, "GET", "/api/liste", {"Host": "boese.example"})[0] == 403
    status, _ = _anfrage(
        server,
        "POST",
        f"/api/stern/{FIRMEN[0][0]}",
        {"Origin": "https://boese.example", "Content-Type": "application/json"},
        b'{"an": true}',
    )
    assert status == 403


def test_dashboard_star_and_note(server, paths: Paths) -> None:  # type: ignore[no-untyped-def]
    isin = FIRMEN[0][0]
    kopf = {"Content-Type": "application/json"}
    assert _anfrage(server, "POST", f"/api/stern/{isin}", kopf, b'{"an": true}')[0] == 200
    assert _anfrage(server, "POST", f"/api/notiz/{isin}", kopf, '{"text": "prüfen"}'.encode())[0]
    d = json.loads(_anfrage(server, "GET", "/api/liste?stern=1")[1])
    assert [z["isin"] for z in d["zeilen"]] == [isin]
    assert dashboard.Merkliste(paths.root).notizen() == {isin: "prüfen"}


def test_freitext_to_filters(paths: Paths) -> None:
    daten = dashboard.Daten(paths)
    f = dashboard.freitext("Tier 1 Aktien aus Deutschland, Note B", daten)
    assert f == {"tier": "1", "note": "B", "land": "DE"}
    f = dashboard.freitext("Technologie aus Nordamerika", daten)
    assert f["region"] == "nordamerika" and f.get("branche") == "Informationstechnik"
