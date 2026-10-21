"""Bauschritt 9: Insider aus SEC Form 4 (SPEC 3.8). Echte Meldungen vom Oktober 2026:

- Intel, David Zinsner (EVP, CFO), 26.01.2026: Kauf am offenen Markt (P) 5.882 Aktien zu
  42,50 USD, Bestand danach 247.392, direkt. Accession 0000050863-26-000032.
- Intel, Lip-Bu Tan (CEO, Director), 11.08.2026: Kauf (P) 105.263 Aktien zu 95,00 USD über einen
  Familientrust (indirekt), Bestand dieser Linie danach 1.314.669. Accession
  0000050863-26-000177.
- Apple, Ben Borders (Principal Accounting Officer), 15.10.2026: Ausübung (M), Steuereinbehalt
  (F) und fünf Verkäufe am offenen Markt (S), alles unter einem Handelsplan nach Rule 10b5-1.
  Zählt nicht.

Handrechnung zum 20.10.2026 (unabhängig mit math nachgerechnet):
- Beide Personen ohne drei Jahre Historie in den Daten: unklar, Gewicht 0,5. Kein Cluster.
- Zinsner: Alter 267 Tage, Abklingen 0,5^(267/90) = 0,12792. Aufstockung
  5.882 / 241.510 = 2,4 % -> Größe max(0,5; 0,024 / 0,10) = 0,5. Rolle CFO 1,0.
  Beitrag 0,5 * 1,0 * 0,5 * 0,12792 = 0,03198.
- Tan: Alter 70 Tage, Abklingen 0,58326. Aufstockung 105.263 / 1.209.406 = 8,7 % -> 0,87037.
  Beitrag 0,5 * 1,0 * 0,87037 * 0,58326 = 0,25383.
- Säule 50 + 20 * (0,03198 + 0,25383) = 55,716.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import yaml

from stockagent.core import insider
from stockagent.data.sources import form4
from tests.sec_fixtures import ROOT

FIX = ROOT / "tests" / "fixtures" / "form4"
CFG = yaml.safe_load((ROOT / "config" / "insider_thresholds.yaml").read_text("utf-8"))
NOW = datetime(2026, 10, 20, tzinfo=UTC)
STICHTAG = date(2026, 10, 20)


def _lesen(datei: str, accession: str, issuer: str = "sec:0000050863") -> list[form4.InsiderTx]:
    return form4.parse_form4(
        (FIX / datei).read_bytes(),
        issuer_id=issuer,
        accession=accession,
        veroeffentlicht=NOW,
        raw_sha256="0" * 64,
        quelle="u",
    )


def _intel() -> list[form4.InsiderTx]:
    return [
        *_lesen("intel-zinsner-2026-01-26.xml", "0000050863-26-000032"),
        *_lesen("intel-tan-2026-08-11.xml", "0000050863-26-000177"),
    ]


def test_form4_parsed_as_reported() -> None:
    z, t = _intel()
    assert (z.person_name, z.rolle, z.code, z.art, z.offener_markt) == (
        "Zinsner David",
        "cfo",
        "P",
        "buy",
        True,
    )
    assert z.stueck == 5882 and z.preis == Decimal("42.50") and z.bestand_danach == 247392
    assert z.handelstag == date(2026, 1, 26) and z.beziehung == "self" and not z.plan_10b5_1
    assert t.rolle == "ceo" and t.beziehung == "indirect" and t.beziehung_text == "by Family Trust"
    assert t.stueck == 105263 and t.preis == Decimal("95.00")
    apple = _lesen("apple-borders-2026-10-15.xml", "0001140361-26-040127", "sec:0000320193")
    assert {x.code for x in apple} >= {"M", "F"} and all(x.plan_10b5_1 for x in apple)
    # Danach Verkäufe am offenen Markt (S) unter dem Handelsplan: routinemäßig, kein Signal
    # (SPEC 3.8 Nr. 3)
    assert {x.code for x in apple if x.offener_markt} == {"S"}
    s = insider.signal("sec:0000320193", apple, STICHTAG, CFG)
    assert s.saeule is None and {g.klasse for g in s.geschaefte} == {"routine"}
    assert form4.xml_name("xslF345X06/form4.xml") == "form4.xml"


def test_signal_by_hand_intel() -> None:
    s = insider.signal("sec:0000050863", _intel(), STICHTAG, CFG)
    assert s.saeule is not None and s.saeule.quantize(Decimal("0.001")) == Decimal("55.716")
    beitraege = {g.person: g.beitrag.quantize(Decimal("0.00001")) for g in s.geschaefte}
    assert beitraege == {"Zinsner David": Decimal("0.03198"), "TAN LIP BU": Decimal("0.25383")}
    assert {g.klasse for g in s.geschaefte} == {"unklar"} and not any(
        g.cluster for g in s.geschaefte
    )


def _wie(x: form4.InsiderTx, tag: date, person: str | None = None) -> form4.InsiderTx:
    return replace(
        x, handelstag=tag, tx_id=f"{x.tx_id}:{tag}:{person}", person_id=person or x.person_id
    )


def test_routine_vs_opportunistic() -> None:
    """Cohen, Malloy, Pomorski: Zinsner handelt im Januar 2023, 2024 und 2025 -> der Kauf im
    Januar 2026 ist routinemäßig (Beitrag 0). Handelt er in den Vorjahren im März, ist der
    Januar-Kauf opportunistisch (Gewicht 1)."""
    z = _intel()[0]
    januar = [_wie(z, date(j, 1, 15)) for j in (2023, 2024, 2025)]
    routine = insider.signal("x", [*januar, z], STICHTAG, CFG)
    assert routine.saeule is None and "routinemäßige" in (routine.grund or "")
    maerz = [_wie(z, date(j, 3, 15)) for j in (2023, 2024, 2025)]
    opp = insider.signal("x", [*maerz, z], STICHTAG, CFG)
    g = next(x for x in opp.geschaefte if x.handelstag == z.handelstag)
    assert g.klasse == "opportunistisch" and g.beitrag.quantize(Decimal("0.00001")) == Decimal(
        "0.06396"
    )  # doppelt so viel wie unklar


def test_cluster_doubles_and_sells_need_cluster() -> None:
    """Drei Personen kaufen innerhalb von 60 Tagen: Cluster, Beitrag doppelt. Ein einzelner
    Verkauf zählt nicht, drei opportunistische Verkäufer in 60 Tagen negativ."""
    t = _intel()[1]
    drei = [t, _wie(t, date(2026, 8, 20), "p2"), _wie(t, date(2026, 9, 1), "p3")]
    s = insider.signal("x", drei, STICHTAG, CFG)
    assert all(g.cluster for g in s.geschaefte)
    original = next(g for g in s.geschaefte if g.handelstag == date(2026, 8, 11))
    assert original.beitrag.quantize(Decimal("0.00001")) == Decimal("0.50766")
    verkauf = replace(t, art="sell", code="S", tx_id="v1")
    assert insider.signal("x", [verkauf], STICHTAG, CFG).saeule is None
    # Drei Verkäufer mit je drei Jahren Historie in anderen Monaten (opportunistisch)
    rows = []
    for n, tag in enumerate((date(2026, 8, 11), date(2026, 8, 25), date(2026, 9, 5))):
        p = f"v{n}"
        rows += [_wie(replace(verkauf, person_id=p), date(j, 3, 1), p) for j in (2023, 2024, 2025)]
        rows.append(_wie(replace(verkauf, person_id=p), tag, p))
    neg = insider.signal("x", rows, STICHTAG, CFG)
    assert neg.saeule is not None and neg.saeule < 50


def test_point_in_time_and_window() -> None:
    """Geschäfte älter als 365 Tage oder nach dem Stichtag zählen nicht."""
    z = _intel()[0]
    alt = _wie(z, STICHTAG - timedelta(days=400))
    assert insider.signal("x", [alt], STICHTAG, CFG).saeule is None
    spaeter = _wie(z, STICHTAG + timedelta(days=1))
    assert insider.signal("x", [spaeter], STICHTAG, CFG).saeule is None


def test_update_loads_new_filings_once(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Einreichungsliste mit zwei Form-4-Meldungen und einem 10-K. Erster Lauf lädt beide XML,
    zweiter Lauf keine (schon gelesen). Nur die XML-Datei ohne Verzeichnis der Stilvorlage."""
    import json

    from stockagent import insider_update
    from stockagent.data import store
    from tests.sec_fixtures import project

    monkeypatch.setenv("SEC_USER_AGENT", "Test Person test@example.com")
    paths = project(tmp_path)
    conn = store.connect(paths.db)
    store.save_isin_cik(
        conn,
        [store.IsinCik("US0378331005", "0000320193", "AAPL", "test", "zugeordnet", "")],
        NOW,
    )
    conn.close()
    sub = {
        "cik": "320193",
        "name": "Apple Inc.",
        "filings": {
            "recent": {
                "accessionNumber": ["0001140361-26-040127", "0001140361-26-040126", "x-10k"],
                "form": ["4", "4", "10-K"],
                "filingDate": ["2026-10-19", "2026-10-19", "2025-10-31"],
                "reportDate": ["2026-10-15", "2026-10-15", "2025-09-27"],
                "acceptanceDateTime": ["2026-10-19T18:30:00.000Z"] * 3,
                "primaryDocument": ["xslF345X06/form4.xml", "xslF345X06/form4.xml", "a.htm"],
            }
        },
    }
    abrufe: list[str] = []

    def fetcher(url: str, agent: str, **_: object) -> bytes:
        abrufe.append(url)
        if "submissions" in url:
            return json.dumps(sub).encode()
        assert url.endswith("/form4.xml") and "xslF345X06" not in url
        return (FIX / "apple-borders-2026-10-15.xml").read_bytes()

    erg = insider_update.update(paths, ["US0378331005"], fetcher=fetcher, now=NOW)
    assert erg[0].meldungen == 2 and erg[0].neu == 2 and erg[0].geschaefte == 14
    assert len(abrufe) == 3
    erg2 = insider_update.update(paths, ["US0378331005"], fetcher=fetcher, now=NOW)
    assert erg2[0].neu == 0 and len(abrufe) == 4  # nur die Einreichungsliste
    conn = store.connect(paths.db)
    try:
        rows = store.load_insider(conn, "sec:0000320193")
        assert len(rows) == 14 and rows[0].veroeffentlicht.tzinfo is not None
        # Vor der Annahme bei der SEC (19.10.2026 18:30 UTC) nicht sichtbar (HR-07)
        assert store.load_insider(conn, "sec:0000320193", datetime(2026, 10, 18, tzinfo=UTC)) == []
    finally:
        conn.close()


def test_insider_pillar_in_rating(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Firma 20 der Bewertungstests mit den beiden Intel-Käufen: Säule Insider 55,716 als
    fester Wert (Rang 'absolut'), Gewicht 10 % im Horizont lang. Ohne Insider-Geschäfte fehlt
    die Säule und senkt die Abdeckung nicht."""
    import json
    import shutil

    from stockagent import bewertung
    from stockagent.data import store
    from stockagent.data.sources import sec as sec_ids
    from stockagent.paths import Paths
    from tests.test_bewertung import FIRMEN, Attrappe, _seed

    shutil.copytree(ROOT / "config", tmp_path / "config")
    p = Paths(tmp_path)
    _seed(p)
    isin, cik = FIRMEN[-1]
    iid = sec_ids.issuer_id(cik)
    conn = store.connect(p.db)
    try:
        for x in _intel():
            store.save_insider(conn, x.accession, iid, [replace(x, issuer_id=iid)], NOW)
    finally:
        conn.close()
    erg = bewertung.bewerten(p, isin, lader=Attrappe().lader(), now=NOW)
    assert erg.grade is not None
    d = json.loads(erg.grade.detail_json or "{}")
    assert Decimal(d["insider"]["saeule"]).quantize(Decimal("0.001")) == Decimal("55.716")
    assert Decimal(d["horizonte"]["lang"]["saeulen"]["insider"]).quantize(
        Decimal("0.001")
    ) == Decimal("55.716")
    ohne = bewertung.bewerten(p, FIRMEN[-2][0], lader=Attrappe().lader(), now=NOW)
    assert ohne.grade is not None
    d2 = json.loads(ohne.grade.detail_json or "{}")
    assert d2["insider"]["saeule"] is None and Decimal(d2["abdeckung"]) > Decimal("0.8")
