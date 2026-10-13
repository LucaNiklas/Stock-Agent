"""Bauschritt 2: Lesen der SEC-, OpenFIGI- und XBRL-Antworten (echte, gekürzte Testdaten)."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from defusedxml import DefusedXmlException

from stockagent.data.sources import openfigi, sec, sec_xbrl
from tests.sec_fixtures import APPLE, JPM, PAGERDUTY, read

# ---------------------------------------------------------------- Tickerliste, Submissions


def test_parse_tickers() -> None:
    rows = {t.ticker: t for t in sec.parse_tickers(read("company_tickers_exchange.json"))}
    assert rows["AAPL"].cik == APPLE and rows["AAPL"].name == "Apple Inc."
    assert rows["JPM-PD"].cik == JPM  # Vorzugsaktie unter derselben CIK


def test_parse_tickers_rejects_unknown_layout() -> None:
    with pytest.raises(sec.SecFormatError):
        sec.parse_tickers(b'{"fields": ["cik", "ticker"], "data": []}')


def test_parse_submissions_master_data() -> None:
    s = sec.parse_submissions(read(f"submissions_{APPLE}.json"))
    assert (s.cik, s.sic, s.fiscal_year_end, s.state_of_incorporation) == (
        APPLE,
        "3571",
        "0926",
        "CA",
    )
    assert s.country == "US" and s.business_region == "CA"
    assert "CUPERTINO" in (s.business_address or "")
    tenk = s.filings["0000320193-25-000079"]
    assert tenk.form == "10-K" and tenk.report_date == date(2025, 9, 27)
    assert tenk.accepted_at == datetime(2025, 10, 31, 14, 1, 26, tzinfo=UTC)


def test_foreign_address_has_no_guessed_country() -> None:
    raw = json.loads(read(f"submissions_{APPLE}.json"))
    raw["addresses"]["business"].update(
        {"stateOrCountry": "2M", "stateOrCountryDescription": "Germany", "city": "WALLDORF"}
    )
    s = sec.parse_submissions(json.dumps(raw).encode())
    assert s.business_region == "2M" and s.country is None
    assert "Germany" in (s.business_address or "")


@pytest.mark.parametrize(
    ("unit", "expected"),
    [
        ("USD", ("monetary", "USD")),
        ("EUR", ("monetary", "EUR")),
        ("shares", ("shares", None)),
        ("USD/shares", ("per_share", "USD")),
        ("pure", ("pure", None)),
        ("Year", None),
        ("USD/Contract", None),
        ("segment", None),
    ],
)
def test_classify_unit(unit: str, expected: tuple[str, str | None] | None) -> None:
    assert sec.classify_unit(unit) == expected


def test_published_at_prefers_acceptance_and_falls_back_to_end_of_day() -> None:
    acc = datetime(2025, 10, 31, 14, 1, 26, tzinfo=UTC)
    assert sec.published_at(date(2025, 10, 31), acc) == acc
    # Ende des Einreichungstags in New York (Sommerzeit, UTC-4)
    ende = datetime(2025, 11, 1, 3, 59, 59, tzinfo=UTC)
    assert sec.published_at(date(2025, 10, 31), None) == ende


def test_parse_companyfacts_keeps_only_report_forms() -> None:
    subs = sec.parse_submissions(read(f"submissions_{PAGERDUTY}.json"))
    forms = frozenset({"10-K", "10-Q"})
    p = sec.parse_companyfacts(
        read(f"companyfacts_{PAGERDUTY}.json"),
        raw_sha256="x",
        retrieved_at=datetime(2026, 10, 13, tzinfo=UTC),
        filings=subs.filings,
        source_url="u",
        report_forms=forms,
    )
    assert {f.form for f in p.facts} <= forms
    assert p.skipped_forms["DEF 14A"] > 0  # Pay-versus-Performance-Tabelle der Proxy
    ni = [
        f
        for f in p.facts
        if f.concept == "us-gaap:NetIncomeLoss"
        and f.period_end == date(2026, 1, 31)
        and f.period_start == date(2025, 2, 1)
    ]
    assert ni and all(f.value == Decimal("173373000") for f in ni)
    f = ni[0]
    assert f.issuer_id == "sec:0001568100" and f.unit == "monetary" and f.currency == "USD"
    assert f.xbrl_context.startswith(f.accession)
    assert p.standard_counts["us-gaap"] > 0 and not p.standard_counts["ifrs-full"]


def test_user_agent_from_env_or_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(sec.MissingUserAgent):
        sec.user_agent(tmp_path)
    (tmp_path / ".env").write_text('SEC_USER_AGENT="Luca Test luca@example.com"\n')
    assert sec.user_agent(tmp_path) == "Luca Test luca@example.com"
    monkeypatch.setenv("SEC_USER_AGENT", "Nur Name ohne Mail")
    with pytest.raises(sec.MissingUserAgent):
        sec.user_agent(tmp_path)


def test_rate_limiter_spaces_requests() -> None:
    now = [0.0]
    waits: list[float] = []

    def sleep(s: float) -> None:
        waits.append(s)
        now[0] += s

    lim = sec.RateLimiter(10, clock=lambda: now[0], sleep=sleep)
    for _ in range(3):
        lim.wait()
    assert waits == pytest.approx([0.1, 0.1])


def test_cik10() -> None:
    assert sec.cik10(320193) == APPLE
    with pytest.raises(sec.SecFormatError):
        sec.cik10("12a")


# ---------------------------------------------------------------- OpenFIGI


def test_openfigi_unique_us_ticker() -> None:
    isins = ["US0378331005", "US69553P1003", "US46625H1005", "US0000000000"]
    res = openfigi.parse_mapping(isins, read("openfigi_mapping.json"))
    assert [r.ticker for r in res] == ["AAPL", "PD", "JPM", None]
    assert "Invalid" in res[3].note


def test_openfigi_multiple_or_no_us_ticker() -> None:
    raw = json.dumps(
        [
            {
                "data": [
                    {"exchCode": "US", "ticker": "BRK/B"},
                    {"exchCode": "US", "ticker": "BRK/A"},
                ]
            },
            {"data": [{"exchCode": "GR", "ticker": "APC"}]},
            {"warning": "No identifier found."},
        ]
    ).encode()
    a, b, c = openfigi.parse_mapping(["A", "B", "C"], raw)
    assert a.ticker is None and "BRK-A, BRK-B" in a.note
    assert b.ticker is None and "kein Ticker" in b.note
    assert c.ticker is None and "No identifier" in c.note


def test_openfigi_rejects_length_mismatch() -> None:
    with pytest.raises(openfigi.FigiFormatError):
        openfigi.parse_mapping(["A", "B"], b"[]")


def test_openfigi_client_batches_and_waits(tmp_path: Path) -> None:
    sent: list[int] = []
    waits: list[float] = []

    def fetcher(url: str, agent: str, **kw: object) -> bytes:
        jobs = json.loads(kw["data"])  # type: ignore[arg-type]
        sent.append(len(jobs))
        return json.dumps([{"warning": "No identifier found."}] * len(jobs)).encode()

    cfg = {
        "mapping_url": "https://api.openfigi.com/v3/mapping",
        "jobs_per_request": 10,
        "requests_per_minute": 25,
    }
    client = openfigi.OpenFigiClient(cfg, "ua", tmp_path, fetcher=fetcher, sleep=waits.append)
    res = client.map([f"I{i}" for i in range(23)])
    assert sent == [10, 10, 3] and len(res) == 23
    assert waits == [2.4, 2.4]  # 60 s / 25 Anfragen
    metas = [json.loads(p.read_text()) for p in tmp_path.glob("*.json")]
    assert any("#I0,I1" in m["url"] for m in metas)  # Anfrage in der Rohablage nachvollziehbar


# ---------------------------------------------------------------- XBRL des Originalberichts


def test_choose_files() -> None:
    names = [i["name"] for i in json.loads(read("aapl_10k_index.json"))["directory"]["item"]]
    assert sec_xbrl.choose_files(names) == ("aapl-20250927_htm.xml", "aapl-20250927_cal.xml")
    # Microsoft bettet die Berechnungsstruktur in das Schema ein
    assert sec_xbrl.choose_files(["FilingSummary.xml", "m.xsd", "m_htm.xml"]) == (
        "m_htm.xml",
        "m.xsd",
    )
    # Ältere Einreichungen ohne Inline-XBRL
    assert sec_xbrl.choose_files(["a-2012.xml", "a-2012_cal.xml", "a-2012_lab.xml"])[0] == (
        "a-2012.xml"
    )
    with pytest.raises(sec_xbrl.XbrlFormatError):
        sec_xbrl.choose_files(["FilingSummary.xml"])


def test_parse_instance_apple_10k() -> None:
    facts = sec_xbrl.parse_instance(read("aapl-20250927_htm.xml"))
    by = {(f.concept, f.period_start, f.period_end): f for f in facts}
    assets = by[("us-gaap:Assets", None, date(2025, 9, 27))]
    assert assets.value == Decimal("359241000000") and assets.unit_raw == "USD"
    assert assets.decimals == -6
    # 10-K-Seite 29: Net income 112.010 Mio. USD
    ni = by[("us-gaap:NetIncomeLoss", date(2024, 9, 29), date(2025, 9, 27))]
    assert ni.value == Decimal("112010000000")
    # Werte mit Dimension (Segmente) werden nicht übernommen
    assert len(facts) == len(set(by))
    assert Counter(f.concept for f in facts)["us-gaap:Assets"] == 2


def test_parse_instance_rejects_other_xml() -> None:
    with pytest.raises(sec_xbrl.XbrlFormatError):
        sec_xbrl.parse_instance(b"<html/>")


def test_parse_instance_refuses_entity_expansion() -> None:
    bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>'
    with pytest.raises(DefusedXmlException):
        sec_xbrl.parse_instance(bomb)


def test_parse_calculation_apple() -> None:
    sums = {s.parent: s for s in sec_xbrl.parse_calculation(read("aapl-20250927_cal.xml"))}
    opex = sums["us-gaap:OperatingExpenses"]
    assert dict(opex.children) == {
        "us-gaap:ResearchAndDevelopmentExpense": Decimal("1.0"),
        "us-gaap:SellingGeneralAndAdministrativeExpense": Decimal("1.0"),
    }
    assert "us-gaap:LiabilitiesAndStockholdersEquity" in sums
