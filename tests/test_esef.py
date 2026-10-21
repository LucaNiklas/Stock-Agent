"""Bauschritt 7: ESEF über filings.xbrl.org (Ausschnitt aus dem echten ESEF-Bericht 2025 von
ASML Holding, asml-2025-12-31-1-en.json, Rohdatei vom 20.10.2026).

Handprüfung gegen den Bericht: verwässertes Ergebnis je Aktie 26,26 EUR (2025), 21,21 EUR (2024),
gewichtete verwässerte Aktienzahl 388,9 Mio. (2025), Bilanzsumme 55.576,8 Mio. EUR am 31.12.2025
und 52.566,5 Mio. EUR am 31.12.2024.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from stockagent.core import abgeleitet
from stockagent.core.calc import Eingabe
from stockagent.data import store
from stockagent.data.sources import esef
from stockagent.paths import Paths
from tests.sec_fixtures import ROOT, project

FIX = ROOT / "tests" / "fixtures" / "esef" / "asml-2025-auszug.json"
LEI = "724500Y6DUVHQD6OXN27"
NOW = datetime(2026, 10, 20, tzinfo=UTC)
EINREICHUNG = esef.Einreichung(
    f"{LEI}-2025-12-31-ESEF-NL-0",
    LEI,
    date(2025, 12, 31),
    "NL",
    "/x.json",
    "",
    datetime(2026, 3, 10, tzinfo=UTC),
    0,
)


def _facts() -> list[store.FactRow]:
    f, _, skip = esef.parse_xbrl_json(
        FIX.read_bytes(), EINREICHUNG, raw_sha256="0" * 64, retrieved_at=NOW, source_url="u"
    )
    assert skip["Dimension"] == 1  # Wert mit Segment-Achse bleibt außen vor
    return f


def test_periods_are_half_open() -> None:
    je = {(f.concept, f.period_start, f.period_end): f for f in _facts()}
    eps = je[("ifrs-full:DilutedEarningsLossPerShare", date(2025, 1, 1), date(2025, 12, 31))]
    assert eps.value == Decimal("26.26") and eps.unit == "per_share" and eps.currency == "EUR"
    # Stand „2026-01-01T00:00:00“ = Bilanz am 31.12.2025
    bilanz = je[("ifrs-full:Assets", None, date(2025, 12, 31))]
    assert bilanz.value == Decimal("55576800000.0") and bilanz.currency == "EUR"
    assert je[("ifrs-full:Assets", None, date(2024, 12, 31))].value == Decimal("52566500000.0")
    aktien = je[("ifrs-full:AdjustedWeightedAverageShares", date(2025, 1, 1), date(2025, 12, 31))]
    assert aktien.unit == "shares" and aktien.currency is None
    assert all(f.issuer_id == f"lei:{LEI}" and f.form == "ESEF" for f in je.values())


def test_filings_list_parsed() -> None:
    raw = (
        b'{"data": [{"attributes": {"period_end": "2025-12-31", "country": "NL", '
        b'"fxo_id": "X-2025", "date_added": "2026-03-10 14:54:03", "json_url": "/a.json", '
        b'"error_count": 0}}, {"attributes": {"period_end": "2024-12-31", "fxo_id": "X-2024", '
        b'"date_added": "2025-03-06 13:27:56", "json_url": "/b.json", "error_count": 2}}]}'
    )
    liste = esef.parse_filings(raw, LEI)
    assert [e.period_end.year for e in liste] == [2024, 2025] and liste[0].fehler == 2


def test_shares_derived_from_eps() -> None:
    """TotalEnergies 2025: kein Aktienwert in ESEF, Ergebnis je Aktie 5,78 USD verwässert."""
    t = date(2025, 12, 31)
    ergebnis = {t: Eingabe(Decimal("13000000000"), "NI", "monetary", t, "USD")}
    eps = {t: Eingabe(Decimal("5.78"), "EPS", "per_share", t, "USD")}
    out = abgeleitet.aktien_aus_eps({}, ergebnis, eps)
    assert out[t].wert.quantize(Decimal(1)) == Decimal("2249134948")
    assert out[t].quelle.startswith("abgeleitet") and out[t].waehrung is None
    fremd = {t: Eingabe(Decimal("5.78"), "EPS", "per_share", t, "EUR")}
    assert abgeleitet.aktien_aus_eps({}, ergebnis, fremd) == {}


def test_issuer_found_via_lei(tmp_path: object) -> None:
    """Heimat-ISIN ohne SEC-Zuordnung: ESEF-Emittent mit derselben LEI, sonst SEC-Melder mit
    derselben LEI (deutsche SAP-Aktie über das ADR)."""
    from pathlib import Path

    paths: Paths = project(Path(str(tmp_path)))
    conn = store.connect(paths.db)
    try:
        conn.execute("UPDATE listings SET lei = 'HWUPKR0MPOU8FGXBT394' WHERE isin = 'US0000000000'")
        assert store.issuer_for_isin(conn, "US0000000000") is None
        conn.execute(
            "INSERT INTO issuers (issuer_id, lei, cik, name, source, source_sha256, retrieved_at) "
            "VALUES ('sec:0000320193', 'HWUPKR0MPOU8FGXBT394', '0000320193', 'Apple', 's', 'x', "
            "now())"
        )
        assert store.issuer_for_isin(conn, "US0000000000") == "sec:0000320193"
        conn.execute(
            "INSERT INTO issuers (issuer_id, lei, name, source, source_sha256, retrieved_at) "
            "VALUES ('lei:HWUPKR0MPOU8FGXBT394', 'HWUPKR0MPOU8FGXBT394', 'Apple', 'esef', 'x', "
            "now())"
        )
        assert store.issuer_for_isin(conn, "US0000000000") == "lei:HWUPKR0MPOU8FGXBT394"
    finally:
        conn.close()
