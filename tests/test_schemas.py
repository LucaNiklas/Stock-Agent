"""HR-04, HR-12: Grundtypen erzwingen Pflichtfelder und erlaubte Quellentypen."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from stockagent.schemas import AccountingStandard, Evidence, Fact, Money, SourceType

LEI = "529900T8BM49AURSDO55"


def fact(**kw: object) -> Fact:
    data: dict[str, object] = {
        "lei": LEI,
        "concept": "us-gaap:Revenues",
        "value": Decimal("1000"),
        "unit": "monetary",
        "currency": "USD",
        "scale": 1_000_000,
        "standard": AccountingStandard.US_GAAP,
        "period_end": date(2025, 12, 31),
        "period_start": date(2025, 1, 1),
        "published_at": datetime(2026, 2, 20, tzinfo=UTC),
        "source_type": SourceType.XBRL,
        "xbrl_context": "FY2025",
    }
    data.update(kw)
    return Fact(**data)  # type: ignore[arg-type]


def test_money_requires_currency_standard_period() -> None:
    with pytest.raises(ValidationError):
        Money(amount=Decimal("1"), scale=1)  # type: ignore[call-arg]
    m = Money(
        amount=Decimal("1.5"),
        currency="EUR",
        scale=1_000_000,
        standard=AccountingStandard.IFRS,
        period_end=date(2025, 12, 31),
    )
    assert m.currency == "EUR"


def test_money_rejects_reversed_period() -> None:
    with pytest.raises(ValidationError):
        Money(
            amount=Decimal("1"),
            currency="EUR",
            scale=1,
            standard=AccountingStandard.IFRS,
            period_end=date(2024, 1, 1),
            period_start=date(2025, 1, 1),
        )


def test_money_accepts_subunit_currency() -> None:
    m = Money(
        amount=Decimal("250"),
        currency="GBX",
        scale=1,
        standard=AccountingStandard.IFRS,
        period_end=date(2025, 12, 31),
    )
    assert m.currency == "GBX"


def test_fact_valid() -> None:
    assert fact().value == Decimal("1000")


@pytest.mark.parametrize(
    ("kw", "reason"),
    [
        ({"currency": None}, "Geldwert ohne Währung"),
        ({"unit": "shares"}, "Aktienanzahl mit Währung"),
        ({"xbrl_context": None}, "XBRL ohne Kontext"),
        ({"source_type": SourceType.PDF_EXTRACTED, "doc_hash": None}, "PDF ohne Dokument"),
        ({"lei": "kurz"}, "LEI falsch"),
    ],
)
def test_fact_rejects_incomplete(kw: dict[str, object], reason: str) -> None:
    with pytest.raises(ValidationError):
        fact(**kw)


def test_schema_rejects_model_knowledge() -> None:
    """HR-04: Vorwissen des Modells ist kein zulässiger Quellentyp."""
    with pytest.raises(ValidationError):
        Evidence(source_type="model_knowledge", metric_ref="roic@2025")  # type: ignore[arg-type]


def test_evidence_needs_anchor() -> None:
    with pytest.raises(ValidationError):
        Evidence(source_type=SourceType.DOCUMENT_TEXT)
