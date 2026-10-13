"""SPEC 3.2: Datenqualitätsprüfungen auf echten Apple-Daten, dazu absichtlich verfälschte Fälle."""

from __future__ import annotations

import dataclasses
from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from stockagent.data import concepts, quality, store
from stockagent.data.sources import sec, sec_xbrl
from tests.sec_fixtures import APPLE, NOW, ROOT, read

ISSUER = f"sec:{APPLE}"
TENK = "0000320193-25-000079"


@pytest.fixture(scope="module")
def apple(tmp_path_factory: pytest.TempPathFactory) -> quality.Kontext:
    conn = store.connect(Path(tmp_path_factory.mktemp("q")) / "q.duckdb")
    subs = sec.parse_submissions(read(f"submissions_{APPLE}.json"))
    cfg = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text())["sec"]
    p = sec.parse_companyfacts(
        read(f"companyfacts_{APPLE}.json"),
        raw_sha256="x",
        retrieved_at=NOW,
        filings=subs.filings,
        source_url="u",
        report_forms=frozenset(cfg["report_forms"]),
    )
    store.replace_facts(conn, ISSUER, p.facts, p.documents)
    bericht = quality.Originalbericht(
        accession=TENK,
        form="10-K",
        stichtag=date(2025, 9, 27),
        instance=sec_xbrl.parse_instance(read("aapl-20250927_htm.xml")),
        calculation=sec_xbrl.parse_calculation(read("aapl-20250927_cal.xml")),
        url="https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/x",
    )
    return quality.Kontext(
        issuer_id=ISSUER,
        as_of=NOW,
        facts=store.pit_query(conn, as_of=NOW, issuer_id=ISSUER),
        restatements=store.restatements(conn, as_of=NOW, issuer_id=ISSUER),
        fiscal_year_end="0926",
        bericht=bericht,
        bericht_facts=store.pit_query(
            conn, as_of=NOW, issuer_id=ISSUER, fassung="einreichung", accession=TENK
        ),
        aktien_erstmeldung=store.pit_query(
            conn,
            as_of=NOW,
            issuer_id=ISSUER,
            concepts=["dei:EntityCommonStockSharesOutstanding"],
            fassung="erste",
        ),
    )


@pytest.fixture(scope="module")
def cmap() -> dict[str, Any]:
    return concepts.load(ROOT / "config")


@pytest.fixture(scope="module")
def cfg() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((ROOT / "config" / "quality.yaml").read_text())
    return data


def by_check(flags: list[store.DqFlag]) -> dict[str, Counter[str]]:
    out: dict[str, Counter[str]] = {}
    for f in flags:
        out.setdefault(f.check_id, Counter())[f.severity] += 1
    return out


def test_apple_passes_all_checks(apple: quality.Kontext, cmap: Any, cfg: Any) -> None:
    flags = quality.run(apple, cmap, cfg)
    sev = by_check(flags)
    assert set(sev) == {f"DQ-0{i}" for i in range(1, 9)}
    assert all(c["ok"] == 1 for c in sev.values())  # jede Prüfung nennt, was sie geprüft hat
    assert not [f for f in flags if f.severity in ("warnung", "stopp")]
    detail = {f.check_id: f.detail for f in flags if f.severity == "ok"}
    assert detail["DQ-01"].startswith("10 Jahresstichtage")
    assert detail["DQ-05"].startswith("9 Kernwerte")


def test_apple_splits_found_from_data(apple: quality.Kontext, cmap: Any, cfg: Any) -> None:
    infos = [f for f in quality.splits(apple, cmap, cfg) if f.severity == "info"]
    assert [f.detail.split(" zwischen")[0][-3:] for f in infos] == ["7:1", "4:1"]


def test_balance_sheet_mismatch_stops(apple: quality.Kontext, cmap: Any, cfg: Any) -> None:
    stichtag = date(2025, 9, 27)
    facts = [
        dataclasses.replace(f, value=f.value * Decimal("1.02"))
        if f.concept == "us-gaap:LiabilitiesAndStockholdersEquity" and f.period_end == stichtag
        else f
        for f in apple.facts
    ]
    ctx = dataclasses.replace(apple, facts=facts)
    stopps = [
        f for f in quality.bilanzgleichung(ctx, cmap, cfg, [stichtag]) if f.severity == "stopp"
    ]
    assert len(stopps) == 1 and "CP-03" in stopps[0].detail
    assert stopps[0].trace_json is not None and "abweichung" in stopps[0].trace_json


def test_second_way_detects_wrong_value(apple: quality.Kontext, cmap: Any, cfg: Any) -> None:
    assert apple.bericht is not None
    inst = [
        dataclasses.replace(f, value=f.value * Decimal("1.06"))
        if f.concept == "us-gaap:Assets" and f.period_end == date(2025, 9, 27)
        else f
        for f in apple.bericht.instance
    ]
    ctx = dataclasses.replace(apple, bericht=dataclasses.replace(apple.bericht, instance=inst))
    flags = [f for f in quality.zweiter_weg(ctx, cmap, cfg) if f.severity != "ok"]
    assert [(f.severity, f.concept) for f in flags] == [("stopp", "us-gaap:Assets")]
    # 2 Prozent Abweichung: Warnung
    inst2 = [
        dataclasses.replace(f, value=f.value * Decimal("1.02"))
        if f.concept == "us-gaap:Assets" and f.period_end == date(2025, 9, 27)
        else f
        for f in apple.bericht.instance
    ]
    ctx = dataclasses.replace(apple, bericht=dataclasses.replace(apple.bericht, instance=inst2))
    flags = [f for f in quality.zweiter_weg(ctx, cmap, cfg) if f.severity != "ok"]
    assert [f.severity for f in flags] == ["warnung"]


def test_sum_structure_detects_broken_total(apple: quality.Kontext, cmap: Any, cfg: Any) -> None:
    assert apple.bericht is not None
    inst = [
        dataclasses.replace(f, value=f.value + Decimal("5000000000"))
        if f.concept == "us-gaap:OperatingExpenses" and f.period_end == date(2025, 9, 27)
        else f
        for f in apple.bericht.instance
    ]
    ctx = dataclasses.replace(apple, bericht=dataclasses.replace(apple.bericht, instance=inst))
    bad = [f for f in quality.summenstruktur(ctx, cmap, cfg) if f.severity != "ok"]
    assert bad and all(f.period_end == date(2025, 9, 27) for f in bad)
    assert any(f.concept == "us-gaap:OperatingExpenses" for f in bad)


def test_missing_report_is_reported(apple: quality.Kontext, cmap: Any, cfg: Any) -> None:
    ctx = dataclasses.replace(apple, bericht=None, bericht_facts=[])
    assert quality.zweiter_weg(ctx, cmap, cfg)[0].severity == "warnung"
    assert quality.summenstruktur(ctx, cmap, cfg)[0].severity == "info"


def test_core_value_in_foreign_currency_warns(apple: quality.Kontext, cmap: Any) -> None:
    facts = [
        dataclasses.replace(f, currency="EUR") if f.concept == "us-gaap:NetIncomeLoss" else f
        for f in apple.facts
    ]
    flags = quality.einheiten(dataclasses.replace(apple, facts=facts), cmap)
    assert any(f.severity == "warnung" and "NetIncomeLoss EUR" in f.detail for f in flags)


def test_restatement_of_core_value_warns(apple: quality.Kontext, cmap: Any) -> None:
    alt = next(
        f
        for f in apple.facts
        if f.concept == "us-gaap:NetIncomeLoss"
        and f.period_end == date(2025, 9, 27)
        and f.period_start is not None
    )
    neu = dataclasses.replace(
        alt,
        value=alt.value - 1,
        accession="0000320193-26-099999",
        form="10-K/A",
        published_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    ctx = dataclasses.replace(apple, restatements=[(alt, neu)])
    flags = quality.restatements(ctx, cmap, quality.jahresstichtage(apple.facts))
    assert [f.severity for f in flags] == ["ok", "warnung"]
    assert "112.010.000.000" in flags[1].detail and "Beide Fassungen" in flags[1].detail


def test_fiscal_year_change_is_flagged(apple: quality.Kontext, cmap: Any, cfg: Any) -> None:
    ctx = dataclasses.replace(apple, fiscal_year_end="1231")
    stichtage = quality.jahresstichtage(apple.facts)[:3]
    flags = quality.perioden(ctx, cmap, cfg, stichtage)
    assert sum(f.severity == "warnung" for f in flags) == 3
