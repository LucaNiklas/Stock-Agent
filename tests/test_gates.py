"""Gates aus SPEC 12.6 mit den Fällen aus HR-01 bis HR-03 und HR-15."""

from typing import Any

import pytest

from stockagent.gates import consistency, evidence, number, quote, schema, wording
from stockagent.schemas import AgentOutput, ClaimStatus, Evidence, SourceType

# ---------------------------------------------------------------- HR-01 Zahlen-Gate


@pytest.mark.parametrize(
    "text",
    [
        "Die Marge liegt bei 23,4 Prozent.",
        "Der Umsatz wuchs um 12%.",
        "Rund 3 Mrd. USD Schulden.",
        "Das KGV von 18 ist hoch.",
        "Umsatz 2025: 1.234 Mio.",
    ],
)
def test_number_gate_rejects_raw_digits(text: str) -> None:
    assert number.offending(text), text


@pytest.mark.parametrize(
    "text",
    [
        "Die Marge liegt bei {{ebit_margin@2025}}.",
        "Seit 2021 steigt revenue_cagr_5y stetig.",
        "Siehe Seite 87 und S. 12-14 im Bericht.",
        "Die Zinsdeckung {{interest_coverage@TTM-2026Q2}} ist komfortabel.",
        "Keine Zahlen hier.",
    ],
)
def test_number_gate_accepts_allowed(text: str) -> None:
    assert number.offending(text) == []


def test_number_gate_year_with_percent_is_not_a_year() -> None:
    assert number.offending("Die Quote stieg auf 2025%.")


def test_number_gate_checks_free_text_fields(claim_factory: Any, output_factory: Any) -> None:
    out = output_factory(claim_factory(text="Die Marge stieg auf 31 Prozent."))
    res = number.check(out)
    assert not res.ok
    assert "claims[0].text" in res.errors[0]


def test_number_gate_ignores_quote_field(claim_factory: Any, output_factory: Any) -> None:
    """Zitate mit Zahlen sind erlaubt, sie prüft das Zitat-Gate."""
    ev = Evidence(
        source_type=SourceType.DOCUMENT_TEXT,
        doc_hash="sha256:ab",
        page=3,
        quote="Umsatz stieg um 12 % auf 4,2 Mrd. EUR.",
    )
    out = output_factory(claim_factory(text="Der Umsatz wuchs deutlich.", evidence=[ev]))
    assert number.check(out).ok


# ---------------------------------------------------------------- HR-02 Beleg-Gate


def test_evidence_gate(claim_factory: Any, output_factory: Any) -> None:
    out = output_factory(claim_factory("c-0001"), claim_factory("c-0002", evidence=[]))
    new, res = evidence.apply(out)
    assert [c.claim_id for c in new.claims] == ["c-0001"]
    assert new.removed_claims[0].claim.claim_id == "c-0002"
    assert new.removed_claims[0].reason == "kein Beleg"
    assert not res.ok


# ---------------------------------------------------------------- HR-03 Zitat-Gate

PAGE = (
    "Im Geschäftsjahr stieg der Umsatz um 12 % auf 4,2 Mrd. EUR. Das Ergebnis wurde durch "
    "Sonderef-\nfekte belastet. „Wir sehen eine robuste Nachfrage“, sagte der Vorstand."
)


def lookup(doc_hash: str, page: int) -> str | None:
    return PAGE if (doc_hash, page) == ("sha256:ab", 3) else None


def _out_with_quote(q: str, output_factory: Any, claim_factory: Any, page: int = 3) -> AgentOutput:
    ev = Evidence(source_type=SourceType.DOCUMENT_TEXT, doc_hash="sha256:ab", page=page, quote=q)
    out: AgentOutput = output_factory(claim_factory(evidence=[ev]))
    return out


@pytest.mark.parametrize(
    "q",
    [
        "der Umsatz um 12 % auf 4,2 Mrd. EUR",
        "durch Sondereffekte belastet",  # Silbentrennung am Zeilenende
        '"Wir sehen eine robuste Nachfrage"',  # andere Anführungszeichen
        "stieg   der\nUmsatz",  # Leerraum
    ],
)
def test_quote_gate_accepts_verbatim(q: str, output_factory: Any, claim_factory: Any) -> None:
    new, res = quote.apply(_out_with_quote(q, output_factory, claim_factory), lookup)
    assert res.ok, res.errors
    assert new.claims[0].status is ClaimStatus.DRAFT


@pytest.mark.parametrize(
    "q",
    [
        "der Umsatz um 13 % auf 4,2 Mrd. EUR",  # Zahl verändert
        "der Umsatz stieg deutlich",  # paraphrasiert
        "DER UMSATZ UM 12 %",  # Schreibweise verändert
    ],
)
def test_quote_gate(q: str, output_factory: Any, claim_factory: Any) -> None:
    new, res = quote.apply(_out_with_quote(q, output_factory, claim_factory), lookup)
    assert not res.ok
    assert new.claims[0].status is ClaimStatus.REJECTED


def test_quote_gate_missing_page(output_factory: Any, claim_factory: Any) -> None:
    out = _out_with_quote("Umsatz", output_factory, claim_factory, page=99)
    new, res = quote.apply(out, lookup)
    assert not res.ok
    assert new.claims[0].status is ClaimStatus.REJECTED


# ---------------------------------------------------------------- HR-15 Formulierungs-Gate


@pytest.mark.parametrize(
    "text",
    [
        "Jetzt kaufen, die Aktie ist günstig.",
        "Kaufen Sie vor der Hauptversammlung.",
        "Unser Kursziel liegt deutlich höher.",
        "Das ist eine klare Kaufempfehlung.",
        "Eine garantierte Rendite ist zu erwarten.",
        "Sie sollten jetzt verkaufen.",
    ],
)
def test_wording_gate(text: str, claim_factory: Any, output_factory: Any) -> None:
    assert not wording.check(output_factory(claim_factory(text=text))).ok


@pytest.mark.parametrize(
    "text",
    [
        "Insiderkäufe des Vorstands häuften sich.",
        "Das Unternehmen kaufte eigene Aktien zurück.",
        "Die Bewertung liegt über dem Branchenmedian.",
    ],
)
def test_wording_gate_allows_neutral(text: str, claim_factory: Any, output_factory: Any) -> None:
    assert wording.check(output_factory(claim_factory(text=text))).ok


# ---------------------------------------------------------------- Schema- und Konsistenz-Gate


def test_schema_gate_reports_errors() -> None:
    obj, res = schema.check('{"envelope": {}}', AgentOutput)
    assert obj is None and not res.ok


def test_schema_gate_rejects_invalid_json() -> None:
    obj, res = schema.check("{kein json", AgentOutput)
    assert obj is None and "JSON" in res.errors[0]


def test_schema_gate_accepts_valid(claim_factory: Any, output_factory: Any) -> None:
    out = output_factory(claim_factory())
    obj, res = schema.check(out.model_dump_json(), AgentOutput)
    assert res.ok and obj == out


def test_consistency_gate() -> None:
    text = "Marge {{ebit_margin@2025}}, Wachstum {{revenue_cagr_5y@2025}}."
    assert consistency.check(text, {"ebit_margin@2025": 0.2, "revenue_cagr_5y@2025": 0.1}).ok
    res = consistency.check(text, {"ebit_margin@2025": 0.2})
    assert res.errors == ["Platzhalter ohne berechneten Wert: revenue_cagr_5y@2025"]
