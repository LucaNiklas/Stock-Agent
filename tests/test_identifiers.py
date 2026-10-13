"""Bauschritt 1: Prüfung von ISIN, Namen, Ländern und Hinterlegungsscheinen (reine Funktionen)."""

from __future__ import annotations

import pytest

from stockagent.core.identifiers import (
    change_exceeds,
    choose_country,
    is_depositary_receipt,
    isin_is_valid,
    names_plausibly_match,
)


@pytest.mark.parametrize(
    "isin",
    [
        "US0378331005",
        "DE0007164600",
        "DE0008404005",
        "GB0002875804",
        "KYG9830T1067",
        "DE000ENER6Y0",
    ],
)
def test_isin_valid(isin: str) -> None:
    assert isin_is_valid(isin)


@pytest.mark.parametrize(
    "isin",
    ["US0378331006", "DE0007164601", "us0378331005", "US037833100", "XX00000000001", ""],
)
def test_isin_invalid(isin: str) -> None:
    assert not isin_is_valid(isin)


@pytest.mark.parametrize(
    ("prev", "cur", "exceeds"),
    [
        (1000, 1050, False),
        (1000, 1051, True),
        (1000, 949, True),
        (1000, 950, False),
        (0, 10, False),
    ],
)
def test_change_exceeds(prev: int, cur: int, exceeds: bool) -> None:
    assert change_exceeds(prev, cur, 5) is exceeds


@pytest.mark.parametrize(
    ("listing", "legal", "match"),
    [
        ("SIEMENS AG NA O.N.", "Siemens Aktiengesellschaft", True),
        ("BAYER ADR /1/4", "Bayer Aktiengesellschaft", True),
        ("S.ENER.ELEC.SP.GDR REGS 1", "SOCIETATEA ENERGETICĂ ELECTRICA S.A.", True),
        ("KAZAKHTELE.ADR1/15/KT1000", "KAZAKHTELECOM JSC", True),
        ("IBM CORP.", "International Business Machines Corporation", True),
        ("MERCURY GENL CORP.", "GRAND PEAK CAPITAL CORP.", False),
        ("ALLIANZ SE NA O.N.", "Allianz SE", True),
        ("SAP SE O.N.", "Siemens Aktiengesellschaft", False),
        ("NU HLDGS  CL.A DL-,000066", "Nu Holdings Ltd.", True),
        ("8X8               DL-,001", "8X8, INC.", True),
        ("3I GROUP PLC   LS-,738636", "3I GROUP PLC", True),
        ("A.P.MOELL.-M.NAM B DK1000", "A.P. MØLLER - MÆRSK A/S", True),
        ("ASAHI GROUP HOLDINGS LTD.", "アサヒグループホールディングス株式会社", False),
        ("ASAHI GROUP HOLDINGS LTD.", "Asahi Group Holdings,Ltd.", True),
        ("CODEXIS INC.       DL-,01", "Cedexis Inc.", False),
        ("STROEER (UNSP.ARD)/4/1", "Ströer SE & Co. KGaA", True),
        ("STROER SE + CO. KGAA", "Ströer SE & Co. KGaA", True),
    ],
)
def test_names_plausibly_match(listing: str, legal: str, match: bool) -> None:
    assert names_plausibly_match(listing, legal) is match


def test_choose_country() -> None:
    # ADR: ISIN-Land US sagt nichts, Hauptsitz laut GLEIF gilt
    assert choose_country("US", "DE", "DE", True, receipt=True) == ("DE", "gleif")
    # Xiaomi: Sitz KY wie ISIN, Hauptsitz CN
    assert choose_country("KY", "KY", "CN", True, receipt=False) == ("CN", "gleif")
    # Steris: irische ISIN, LEI der alten britischen Gesellschaft
    assert choose_country("IE", "GB", "GB", True, receipt=False) == ("IE", "konflikt")
    assert choose_country("US", "CA", "CA", False, receipt=False) == ("US", "isin")
    assert choose_country("KY", None, None, False, receipt=False) == ("KY", "isin")


@pytest.mark.parametrize(
    ("name", "receipt"),
    [
        ("BAYER ADR /1/4", True),
        ("PHARMING GRP SP. ADRS", True),
        ("LIFE360 INC.CDIS/3 O.N.", True),
        ("WALT DISNEY CO. CDR O.N.", True),
        ("AUTOLIV SDR/1 DL-,01", True),
        ("ASML HOLDING NY    EO-,09", True),
        ("HARMONY GD MNG ADRRC,-50", True),
        ("KESORAM IND.LTD GDRREGS/1", True),
        ("NIPPON YUSEN K.K.SP.DR1/5", True),
        ("SIEMENS AG NA O.N.", False),
        ("ADIDAS AG NA O.N.", False),
        ("CADELER A/S DK 1", False),
        ("NYRSTAR", False),
        ("RECKITT BENCKISER ADRO.N", True),
        ("DOWNER EDI LTD.UNSP. 2", True),
        ("ADRIATIC METALS PLC", False),
    ],
)
def test_is_depositary_receipt(name: str, receipt: bool) -> None:
    assert is_depositary_receipt(name) is receipt
