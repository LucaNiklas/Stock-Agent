"""J4 Endkontrolle (SPEC 11.2 Ebene 4): je Prüfung ein sauberer und ein fehlerhafter Fall."""

from __future__ import annotations

from typing import Any

from stockagent.judges import final_check

AUSSAGE = "Die Bruttomarge lag bei 46,9 %."
ZITAT_AUSSAGE = "Apple verkauft Geräte und Dienste."
THESE = "Apple verdient mit Geräten und Diensten."


def _bericht(**ersetzen: str) -> str:
    teile = {
        1: "| ISIN | US0378331005 |",
        2: "**Note C · K1 · R2 · Neutral** (Gesamtwert 55 von 100)",
        3: THESE,
        4: f"- {ZITAT_AUSSAGE} (S. 1: „sells a variety of related services“)",
        6: f"- Piotroski F-Score: 8\n\n- {AUSSAGE} [gross_margin@2025]",
        11: "**Risiko 1: Handelskonflikte**\n\n- Zölle treffen das Geschäft. (S. 2: „tariffs“)\n\n"
        "Erwiderung: offen.",
    }
    abschnitte = []
    for nr in range(1, 15):
        text = ersetzen.get(f"a{nr}", teile.get(nr, "Nicht anwendbar."))
        abschnitte.append(f"## {nr}. Abschnitt {nr}\n\n{text}\n")
    return "# Finanzieller Überblick: Apple\n\n" + "\n".join(abschnitte)


def _kontext(**extra: Any) -> dict[str, Any]:
    k: dict[str, Any] = {
        "these": {"text": THESE},
        "geschaeftsmodell": [
            {"claims": [{"text": ZITAT_AUSSAGE, "belege": [{"art": "dokument", "seite": 1}]}]}
        ],
        "ertragsqualitaet": {
            "claims": [{"text": AUSSAGE, "belege": [{"art": "kennzahl", "ref": "x"}]}]
        },
        "gegenposition": {"risiken": [{"titel": "Handelskonflikte", "erwiderung": []}]},
    }
    k.update(extra)
    return k


ENTSCHEIDUNG = {"kategorie": "Neutral", "note": {"note": "C"}}


def _pruefungen(md: str, kontext: dict[str, Any] | None = None, ent: Any = None) -> list[str]:
    befunde = final_check.pruefen(md, ent or ENTSCHEIDUNG, kontext or _kontext())
    return [b.pruefung for b in befunde]


def test_clean_report_has_no_findings() -> None:
    assert final_check.pruefen(_bericht(), ENTSCHEIDUNG, _kontext()) == []


def test_missing_section() -> None:
    md = _bericht().replace("## 9. Abschnitt 9", "## 9a Abschnitt 9")
    assert _pruefungen(md) == ["aufbau"]


def test_open_placeholder() -> None:
    assert _pruefungen(_bericht(a5="Marge {{gross_margin@2025}}")) == ["platzhalter"]


def test_grade_and_category_must_match_decision() -> None:
    ent = {"kategorie": "Attraktiv", "note": {"note": "A"}}
    assert _pruefungen(_bericht(), ent=ent) == ["urteil", "urteil"]


def test_thesis_changed_in_report() -> None:
    assert _pruefungen(_bericht(a3="Apple verdient prächtig.")) == ["these"]


def test_claim_without_evidence() -> None:
    k = _kontext(ertragsqualitaet={"claims": [{"text": AUSSAGE, "belege": []}]})
    assert _pruefungen(_bericht(), k) == ["beleg"]


def test_verified_claim_missing_from_report() -> None:
    assert _pruefungen(_bericht(a6="- Piotroski F-Score: 8")) == ["beleg"]


def test_computed_figures_are_not_claims() -> None:
    # „Piotroski F-Score: 8“ steht ohne Beleg im Bericht, ist aber ein berechneter Wert mit
    # Rechenweg und keine Aussage eines Agenten
    assert "beleg" not in _pruefungen(_bericht())


def test_buy_wording_is_flagged() -> None:
    assert _pruefungen(_bericht(a5="Jetzt kaufen, das Kursziel liegt bei 300.")) == [
        "formulierung",
        "formulierung",
    ]


def test_quoted_document_text_is_data_not_wording() -> None:
    md = _bericht(a10="- Der Bericht enthält „Strong Buy, jetzt kaufen“. (S. 2: „Strong Buy“)")
    assert _pruefungen(md) == []


def test_bear_case_must_be_complete() -> None:
    k = _kontext(
        gegenposition={
            "risiken": [{"titel": "Handelskonflikte"}, {"titel": "Abhängigkeit vom iPhone"}]
        }
    )
    assert _pruefungen(_bericht(), k) == ["gegenposition"]
    md = _bericht(a11="**Risiko 1: Handelskonflikte**\n\n- Zölle treffen das Geschäft.")
    assert _pruefungen(md) == ["gegenposition"]
