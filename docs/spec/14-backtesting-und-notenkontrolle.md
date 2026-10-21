## 14. Backtesting und Notenkontrolle

### 14.1 Was rückwärts testbar ist

Nur der deterministische Teil (Klassifikation, Kennzahlen, Scores, Noten) wird historisch getestet, mit Point-in-Time-Daten ab 2010 für US-Werte und ab 2020 für ESEF-Werte. LLM-Urteile werden nicht rückwärts getestet, weil die Modelle die Kursentwicklung aus dem Training kennen. Die Literatur dazu (Glasserman und Lin 2023, Sarkar und Vafa 2024, He et al. zu ChronoGPT 2025) zeigt, dass das Ausmaß der Verzerrung von Modell und Anwendung abhängt und nie sicher null ist.

Regeln für den Backtest. Keine Überlebensverzerrung (delistete Titel bleiben mit Endwert drin), keine Optimierung der Gewichte auf dem Testzeitraum. Wer Gewichte verändert, testet auf einem getrennten Zeitraum.

### 14.2 Notenkontrolle (vorwärts)

Sobald die ersten quantitativen Noten vorliegen (Schritt 5 in 16.10), friert das System bei jedem Lauf die Noten aller bisher bewerteten Unternehmen mit Datum ein (`grade_snapshots`, Bewertung auf Anfrage nach ADR 0005). Es misst danach, wie sich die Kurse je Notenstufe entwickeln, gegen einen breiten Vergleichsindex. Das ist eine reine Messung der Methodik, kein Depot und keine Allokation. Je früher sie startet, desto früher gibt es eine belastbare Aussage.

### 14.3 Erfolgsmaße

- Rendite je Notenstufe nach 6, 12 und 24 Monaten gegen den Vergleichsindex, je Anlagehorizont (6.2): Horizont kurz vor allem nach 6 und 12 Monaten, mittel nach 12 und 24 Monaten. Die Noten aller Horizonte stehen im Tagesstand (`grade_snapshots.horizonte_json`).
- Rangkorrelation (Spearman) zwischen Note und Folgerendite.
- Prüferqualität aus 11.6.
- Kosten je Lauf.

### 14.4 Überprüfungskriterium (vorab festgelegt)

Ordnen die Noten nach 24 Monaten die Folgerenditen nicht monoton (A besser als B besser als C), wird die Methodik in einem getrennten Zeitraum überprüft und eine Änderung als neue Methodik-Version eingeführt. Das Kriterium steht in `config/scoring.yaml` und wird nicht nachträglich verschoben. Grund ist Bessembinders Befund (Abschnitt 1, Nr. 12). Ohne vorab festgelegtes Kriterium neigt man dazu, schwache Ergebnisse wegzuerklären.
