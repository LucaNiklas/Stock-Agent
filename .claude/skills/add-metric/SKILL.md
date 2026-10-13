---
name: add-metric
description: Neue Finanzkennzahl in das Formelregister aufnehmen, schrittweise mit Rechenweg und Prüfpunkten (HR-19). Verwenden, wenn Luca sagt "füge Kennzahl X hinzu" oder eine Kennzahl aus SPEC 3.3 gebaut wird. Voraussetzung ist core/calc.py aus Bauschritt 2.
---

# Kennzahl hinzufügen

Verbindlich sind SPEC 3.3, 12.2, 12.7 und 18.1 sowie die harten Regeln HR-01, HR-06, HR-12 und HR-19 (`docs/spec/00-arbeitsanweisung.md`). Gibt es `src/stockagent/core/calc.py` noch nicht, abbrechen und Luca sagen, dass zuerst der Rechenweg aus Bauschritt 2 gebaut werden muss.

## Ablauf

1. **Definition klären, bevor Code entsteht.**
   - Fachliche oder akademische Quelle der Formel nennen (Lehrbuch, Paper). Keine Formel aus dem Gedächtnis übernehmen, ohne sie an der Quelle zu prüfen.
   - Eingaben als interne Größen festlegen (`config/concept_map.yaml`). Fehlt eine Größe, erst dort ergänzen.
   - Richtung festlegen: `higher_better`, `lower_better` oder Zielband.
   - Sonderfälle festlegen: negativer Nenner, fehlende Perioden, Banken und Versicherer (andere Scorecard).
   - Dem Nutzer die Definition zeigen und Freigabe abwarten.

2. **Rechenweg mit Prüfpunkten entwerfen (HR-19).** Die Formel in kleine benannte Schritte zerlegen. Nach jedem Abschnitt mindestens einen Prüfpunkt aus dem Katalog CP-01 bis CP-08 (SPEC 12.7):
   - CP-01 vor dem ersten Schritt: gleiche Währung, Einheit, Skalierung, Periode, Rechnungslegung.
   - CP-02 nach jedem Zwischenergebnis: Vorzeichen und Wertebereich.
   - CP-03, wenn Teile eine Summe bilden.
   - CP-04, wenn es einen zweiten Rechenweg gibt.
   - CP-05 am Ende als Warnung gegen die eigene Historie.

3. **Registereintrag in `config/metrics.yaml`** mit allen Feldern aus SPEC 12.2: `id`, `version`, `name`, `formel`, `definition`, `eingaben`, `einheit`, `richtung`, `rundung`, `scorecards`, `quelle`, `pruefpunkte`, `tests`.

4. **Test zuerst schreiben** (`tests/metrics/test_<id>.py`):
   - Handrechnung aus einem echten Bericht (10-K oder Geschäftsbericht). Dokument und Seite im Kommentar je Eingabewert.
   - Jedes Zwischenergebnis des Rechenwegs einzeln prüfen, nicht nur das Endergebnis.
   - Ein Fall mit verletztem Prüfpunkt: Die Rechnung stoppt, das Ergebnis ist `unknown` mit Grund, INC-15 wird erzeugt.
   - Ein Fall mit fehlender Eingabe: `unknown`, kein Schätzwert (HR-05).

5. **Funktion in `src/stockagent/core/registry.py`** mit `@metric("<id>")`. Sie rechnet ausschließlich über den Rechenweg aus `core/calc.py` und nutzt `Decimal` für Geldbeträge. Gerundet wird erst bei der Anzeige.

6. **Prüfen:** `uv run pytest`, `uv run ruff check .`, `uv run mypy`. Der Test `test_registry_matches_metrics_yaml` muss grün sein.

7. **Methodik dokumentieren**, falls die Kennzahl in die Note eingeht: Gewicht in `config/scoring.yaml`, Eintrag in `docs/METHODOLOGY_CHANGELOG.md`, `methodology_version` erhöhen. Der PR bekommt das Label `methodology`.

## Nicht erlaubt

- Arithmetik außerhalb von `src/stockagent/core/` (HR-06).
- Weiterrechnen nach einem verletzten Prüfpunkt (HR-19).
- Zahlen aus Vorwissen statt aus einem Bericht (HR-04).
