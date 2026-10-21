"""Jury J3 (SPEC 11.2 Ebene 3, 11.3, 11.4): Aggregation über den Rechenweg, Anonymisierung."""

from __future__ import annotations

from decimal import Decimal

from stockagent.agents.eingaben import anonymisieren
from stockagent.core import jury

CFG = jury.JuryKonfig(Decimal(3), Decimal(4), Decimal(2), 2)


def _alle(*punkte: int) -> dict[str, list[int]]:
    return {k: list(punkte) for k in jury.KRITERIEN}


def test_hand_calculation_median_and_range() -> None:
    # Punkte 4, 5, 3: sortiert 3, 4, 5, Median 4. Spannweite 5 - 3 = 2, nicht über 2: einig
    erg = jury.urteil(_alle(4, 5, 3), CFG)
    assert erg.status == "verified" and erg.richter == 3
    k = erg.kriterien[0]
    assert (k.median, k.spannweite) == (Decimal(4), Decimal(2))


def test_range_above_two_means_divided_jury() -> None:
    # 5, 2, 4: Spannweite 3 > 2, Median 4
    erg = jury.urteil(_alle(5, 2, 4), CFG)
    assert erg.status == "escalated"
    assert erg.gruende[0] == "faktentreue: Jury uneinig (Spannweite 3)"


def test_overall_reasoning_needs_median_four() -> None:
    punkte = _alle(4, 4, 4)
    punkte["gesamtbegruendung"] = [3, 3, 4]
    erg = jury.urteil(punkte, CFG)
    assert erg.status == "escalated"
    assert erg.gruende == ["gesamtbegruendung: Median 3 unter 4"]


def test_no_criterion_below_three() -> None:
    punkte = _alle(4, 4, 4)
    punkte["bewertungsdisziplin"] = [2, 3, 2]
    erg = jury.urteil(punkte, CFG)
    assert erg.gruende == ["bewertungsdisziplin: Median 2 unter 3"]


def test_two_judges_median_is_mean_of_middle() -> None:
    # Ein Richter ohne Urteil: Median aus 4 und 5 ist 4,5, Spannweite 1
    erg = jury.urteil(_alle(4, 5), CFG)
    assert erg.kriterien[0].median == Decimal("4.5")
    assert erg.status == "verified"
    # 3 und 4: Median 3,5 liegt unter 4 für die Gesamtbegründung
    assert jury.urteil(_alle(3, 4), CFG).gruende == ["gesamtbegruendung: Median 3.5 unter 4"]


def test_one_judge_is_not_a_jury() -> None:
    erg = jury.urteil(_alle(5), CFG)
    assert erg.status == "escalated" and erg.gruende == ["nur 1 Richter geurteilt, nötig 2"]


def test_points_outside_scale_stop_the_calculation() -> None:
    # CP-02: Punkte außerhalb 1 bis 5 stoppen die Rechnung, kein Ergebnis aus fehlerhaften Werten
    erg = jury.urteil(_alle(4, 6, 4), CFG)
    assert erg.status == "escalated"
    assert erg.kriterien[0].median is None
    assert "CP-02" in erg.gruende[0]


def test_anonymize_company_name() -> None:
    anon = anonymisieren("Apple Inc.")
    assert anon("Apple Inc. verkauft Geräte. APPLE wächst.") == (
        "das Unternehmen verkauft Geräte. das Unternehmen wächst."
    )
    assert anonymisieren("JPMorgan Chase & Co.")("JPMorgan verdient an Zinsen.") == (
        "das Unternehmen verdient an Zinsen."
    )
    # Kurze erste Wörter bleiben, sonst würde „Dow“ jedes Wort „Dow“ in Indizes treffen
    assert anonymisieren("Dow Inc.")("Der Dow Jones fiel, Dow Inc. auch.") == (
        "Der Dow Jones fiel, das Unternehmen auch."
    )
