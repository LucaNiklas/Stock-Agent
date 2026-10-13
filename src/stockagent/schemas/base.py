"""Grundtypen.

HR-12: `Money` und `Fact` sind ohne Währung, Einheit, Rechnungslegungsstandard und Periode
nicht konstruierbar. HR-04: Der Quellentyp `model_knowledge` existiert nicht.
HR-01: Freitext von Agenten trägt den Marker `FREE_TEXT`, damit das Zahlen-Gate ihn findet.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _FreeTextMarker:
    """Kennzeichnet Felder, in denen ein Sprachmodell Freitext schreibt."""

    def __repr__(self) -> str:
        return "FREE_TEXT"


FREE_TEXT = _FreeTextMarker()

FreeText = Annotated[str, Field(max_length=2000), FREE_TEXT]

CurrencyCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$|^GBX$|^ZAc$|^ILA$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AccountingStandard(StrEnum):
    IFRS = "IFRS"
    US_GAAP = "US-GAAP"
    HGB = "HGB"
    LOCAL_OTHER = "local_other"


class SourceType(StrEnum):
    XBRL = "xbrl"
    PDF_EXTRACTED = "pdf_extracted"
    VENDOR = "vendor"
    DOCUMENT_TEXT = "document_text"


class Money(_Strict):
    amount: Decimal
    currency: CurrencyCode
    scale: Literal[1, 1_000, 1_000_000, 1_000_000_000]
    standard: AccountingStandard
    period_end: date
    period_start: date | None = None

    @model_validator(mode="after")
    def _period_order(self) -> Money:
        if self.period_start is not None and self.period_start > self.period_end:
            raise ValueError("period_start liegt nach period_end")
        return self


class Fact(_Strict):
    """Ein Wert aus einer Quelle (Datenmodell `facts`, SPEC 7.7)."""

    # `sec:<CIK>` für SEC-Melder, `lei:<LEI>` für Emittenten ohne CIK (SPEC 7.7)
    issuer_id: str = Field(pattern=r"^(sec:\d{10}|lei:[A-Z0-9]{20})$")
    concept: str = Field(min_length=1)
    value: Decimal
    unit: Literal["monetary", "shares", "per_share", "pure", "ratio"]
    currency: CurrencyCode | None
    scale: Literal[1, 1_000, 1_000_000, 1_000_000_000]
    standard: AccountingStandard
    period_end: date
    period_start: date | None
    published_at: datetime
    source_type: SourceType
    doc_hash: str | None = None
    page: int | None = Field(default=None, ge=1)
    xbrl_context: str | None = None

    @model_validator(mode="after")
    def _currency_rules(self) -> Fact:
        if self.unit in ("monetary", "per_share") and self.currency is None:
            raise ValueError("Geldwerte brauchen eine Währung")
        if self.unit in ("shares", "pure", "ratio") and self.currency is not None:
            raise ValueError("Mengen und Verhältnisse haben keine Währung")
        if self.source_type is SourceType.XBRL and not self.xbrl_context:
            raise ValueError("XBRL-Werte brauchen einen Kontext")
        if self.source_type is SourceType.PDF_EXTRACTED and (not self.doc_hash or not self.page):
            raise ValueError("Extrahierte Werte brauchen doc_hash und Seite")
        return self


class Evidence(_Strict):
    """Beleg für eine Aussage: Dokumentstelle mit wörtlichem Zitat oder Kennzahl."""

    source_type: SourceType
    doc_hash: str | None = None
    page: int | None = Field(default=None, ge=1)
    quote: str | None = Field(default=None, max_length=1500)
    metric_ref: str | None = None

    @model_validator(mode="after")
    def _has_anchor(self) -> Evidence:
        if self.metric_ref is None and (self.doc_hash is None or self.page is None):
            raise ValueError("Beleg braucht metric_ref oder doc_hash mit Seite")
        return self


class ClaimStatus(StrEnum):
    DRAFT = "draft"
    CHECKED = "checked"
    VERIFIED = "verified"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class Claim(_Strict):
    claim_id: str = Field(pattern=r"^c-\d{4}$")
    text: FreeText
    type: Literal["quantitative", "qualitative"]
    metric_refs: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    confidence_level: Literal["hoch", "mittel", "niedrig"]
    status: ClaimStatus = ClaimStatus.DRAFT


class RemovedClaim(_Strict):
    claim: Claim
    reason: str


class Envelope(_Strict):
    run_id: str
    agent_id: str
    agent_version: str
    prompt_hash: str
    model_class: Literal["fast", "standard", "strong", "extern"]
    model: str
    lei: str | None = None
    input_refs: list[str] = Field(default_factory=list)
    created_at: datetime
    status: ClaimStatus = ClaimStatus.DRAFT


class AgentOutput(_Strict):
    envelope: Envelope
    claims: list[Claim] = Field(default_factory=list)
    removed_claims: list[RemovedClaim] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
