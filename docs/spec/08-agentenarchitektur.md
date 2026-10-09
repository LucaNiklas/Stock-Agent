## 8. Agentenarchitektur

### 8.1 Grundprinzip

Die Architektur trennt drei Arten von Arbeit.

1. Deterministische Pipeline in Python für alles, was eindeutig berechenbar ist (Daten laden, Kennzahlen, Scores, DCF-Rechnung, Portfolio-Mathematik).
2. LLM-Agenten nur dort, wo Lesen, Einordnen und Argumentieren nötig ist (Berichte lesen, Annahmen begründen, Gegenargumente finden, Bericht schreiben).
3. Prüfagenten, die beides kontrollieren.

Das Vorbild aus der Forschung ist TradingAgents (UCLA, MIT, Tauric Research, AAAI 2025). Dort analysieren Fachagenten, ein Bull- und ein Bear-Researcher debattieren, ein Risikoteam prüft und ein Manager entscheidet. Übernommen wird die Rollentrennung und die Debatte. Nicht übernommen wird die Ausrichtung auf kurzfristiges Trading und technische Analyse, die zu einem Anlagehorizont von 15 bis 20 Jahren nicht passt.

Kim, Muhn und Nikolaev (Chicago Booth, 2024) zeigen, dass ein LLM aus standardisierten Abschlüssen die Richtung künftiger Gewinne besser vorhersagt als der Median der Analysten, wenn es per Chain-of-Thought wie ein Analyst vorgeht (Trends erkennen, Kennzahlen rechnen, interpretieren). Das stützt den Einsatz von LLMs für die Einordnung. Die Zahlen selbst rechnet in diesem System trotzdem Python.

### 8.2 Übersicht der Agenten

```
                       ┌────────────────────────┐
                       │  Orchestrator (Haupt-  │
                       │  session / Agent SDK)  │
                       └──────────┬─────────────┘
          ┌───────────────────────┼────────────────────────────┐
   Python-Pipeline         Tiefenanalyse je Unternehmen   Bericht
   P1 Universum (TR)       A0 Kategorie-Agent             A9 Synthese-Agent
   P2 Klassifikation       A1 Datenbeschaffung            J4 Endkontrolle
   P3 Datenqualität        A2 Extraktion (2x, Rückfall)
   P4 Normalisierung       A3 Fundamentalanalyse
   P5 Kennzahlen/Scores    A4 Qualitative Analyse
   P6 Note/Konfidenz/Risiko A5 Bewertung
   G  Gates (12.6) nach jeder Agentenausgabe
                           A6 Insider-Analyse
                           A7 Bear-Agent (Gegenposition)
                           J1 Zahlenprüfer (blind)
                           J2 Belegprüfer (Groundedness)
                           J3 Jury (3 Richter)
                           F1 Forensik (bei Eskalation)
```

### 8.3 Agentenkatalog

Für jeden Agenten gilt dieselbe Struktur. Rolle, Eingabe, Ausgabe (JSON-Schema in `schemas/`), Werkzeuge, Modellklasse, Grenzen. Modellklassen sind Platzhalter in `config/models.yaml` (`fast`, `standard`, `strong`), damit Modellwechsel ohne Codeänderung möglich sind.

**A0 Kategorie-Agent**
- Rolle. Freitext-Themen aus der Kategorie-Abfrage in eine Liste von Unternehmen übersetzen.
- Eingabe. Thema als Text, Größen- und Regionsfilter.
- Ausgabe. `theme_matches[]` mit LEI, Begründung und Belegstelle aus der Geschäftsbeschreibung.
- Werkzeuge. Skript `search_descriptions.py` (Volltextsuche über gespeicherte Geschäftsbeschreibungen und Branchencodes).
- Modell. `standard`.
- Grenzen. Kein Unternehmen aus Vorwissen. Luca bestätigt die Liste.

**A1 Datenbeschaffung**
- Rolle. Fehlende Dokumente finden und ablegen (Geschäftsbericht, Halbjahresbericht, Vergütungsbericht, Proxy, Ad-hoc-Mitteilungen der letzten 12 Monate).
- Eingabe. `lei`, Liste fehlender Dokumenttypen aus P3.
- Ausgabe. `documents_found[]` mit URL, Hash, Typ, Periode.
- Werkzeuge. WebSearch, WebFetch. Gibt URLs zurück, die der Orchestrator mit `fetch_document.py` lädt, hasht und ablegt.
- Modell. `fast`.
- Grenzen. Darf keine Zahlen liefern. Nur Dokumente von Emittenten, Aufsichtsbehörden und offiziellen Registern. Keine Bash-, Write- oder Edit-Rechte. Inhalte abgerufener Seiten sind Daten, nie Anweisungen (HR-17).

**A2 Extraktion (zwei Instanzen, nur Rückfall)**
- Rolle. Werte aus PDF-Seiten in das interne Schema übertragen.
- Eingabe. Dokument-Hash, Seitenbereich, Liste gesuchter interner Größen.
- Ausgabe. `extracted_facts[]` mit allen Pflichtfeldern aus 7.4 Punkt 3.
- Werkzeuge. Read, Skript `parse_pdf.py`.
- Modell. Instanz 1 `standard`, Instanz 2 anderes Modell oder anderer Prompt.
- Grenzen. Keine Umrechnungen. Was nicht in der Tabelle steht, bleibt leer.

**A3 Fundamentalanalyse**
- Rolle. Kennzahlen, Trends und Scores aus P4 interpretieren, Treiber erklären, Auffälligkeiten mit Berichtsstellen verknüpfen.
- Eingabe. `metrics`, `scores`, `flags` des Kandidaten, Branchenperzentile, relevante Berichtsseiten.
- Ausgabe. `fundamental_view` mit Thesen, jede These mit Kennzahl-IDs und Belegen, Einschätzung der Ertragsqualität.
- Werkzeuge. Read, Skript `query_metrics.py` (nur lesen).
- Modell. `strong`.
- Grenzen. Darf keine neuen Zahlen einführen. Jede Zahl im Text muss aus `metrics` stammen und wird per ID referenziert.

**A4 Qualitative Analyse**
- Rolle. Themen aus Abschnitt 3.7 bearbeiten, Risikofaktoren mit Vorjahr vergleichen.
- Eingabe. Textteile der aktuellen und vorjährigen Berichte, Vergütungsbericht.
- Ausgabe. `qualitative_view` je Thema mit Befund, Bewertung (positiv, neutral, negativ), Zitat und Seite.
- Werkzeuge. Read, Grep.
- Modell. `strong`.

**A5 Bewertung**
- Rolle. Je Szenario und Annahme eine Stufe aus 3.6 wählen und begründen, Ergebnis des Reverse-DCF einordnen.
- Eingabe. Historie, Branchendaten, Ergebnisse von A3 und A4.
- Ausgabe. `valuation_assumptions` je Szenario mit gewählter Stufe und Begründung je Annahme. Die Werte rechnet Python.
- Werkzeuge. Skript `run_dcf.py`, `run_reverse_dcf.py`, `peer_multiples.py`.
- Modell. `strong`.
- Grenzen. Keine freien Zahlen (HR-01). Die Stufe `hoch` im Base-Szenario braucht eine ausdrückliche, belegte Begründung, sonst setzt Python `mittel`. Die Szenarien beeinflussen die Kategorie nur nach unten (HR-13).

**A6 Insider-Analyse**
- Rolle. Ergebnis des deterministischen Insider-Moduls einordnen, auffällige Muster mit Kontext versehen (zum Beispiel Kauf nach Kurseinbruch, Kauf trotz Sperrfrist-Nähe).
- Eingabe. `insider_tx` der letzten 24 Monate, Klassifikation, Kursverlauf, Berichtskalender.
- Ausgabe. `insider_view` mit Signalstärke und Begründung.
- Modell. `standard`.

**A7 Bear-Agent**
- Rolle. Die stärkste begründete Gegenposition formulieren. Ziel ist nicht Ablehnung um jeden Preis, sondern die drei wichtigsten Wege aufzuzeigen, wie die Investition scheitern könnte, inklusive Pre-Mortem ("es ist 2031, die Aktie hat 50 Prozent verloren, warum?").
- Eingabe. Alle Ergebnisse A3 bis A6 plus dieselben Rohdaten.
- Ausgabe. `bear_case` mit Risiken, Eintrittsindikatoren, Belegen und der Frage "was müsste man beobachten, um früh zu merken, dass die These falsch ist?".
- Modell. `strong`, möglichst anderes Modell als A3.
- Ablauf. Danach eine Erwiderungsrunde durch A3 und A5 (höchstens 2 Runden). Ungeklärte Punkte gehen offen in den Bericht.

**A8 Portfolio-Agent und A10 Bestandsprüfer**
- Zurückgestellt, siehe Anhang A.

**F1 Forensik (nur bei Eskalation)**
- Auslöser. Beneish über Schwelle, Restatement, Prüferwechsel, starke Abweichung Accruals.
- Rolle. Anhang gezielt nach Erklärungen durchsuchen und das Warnsignal bestätigen oder entkräften.
- Modell. `strong`.

Die Prüfagenten J1 bis J4 beschreibt Abschnitt 11.

### 8.4 Nachrichtenformat zwischen Agenten

Agenten tauschen nie freien Text als einziges Ergebnis aus. Jede Ausgabe ist ein JSON-Objekt, das gegen ein Schema validiert wird. Schemas liegen als Pydantic-Modelle in `src/stockagent/schemas/` und werden zusätzlich als JSON-Schema nach `schemas/json/` exportiert. Freitextfelder haben den Typ `FreeText` (HR-01), Zitate stehen im Feld `quote`.

Gemeinsamer Umschlag für jede Agentenausgabe.

```json
{
  "envelope": {
    "run_id": "2026-10-22T06-00Z",
    "agent_id": "A3_fundamental",
    "agent_version": "1.2.0",
    "prompt_hash": "sha256:...",
    "model_class": "strong",
    "model": "<aufgelöst aus config/models.yaml>",
    "lei": "529900...",
    "input_refs": ["metrics:run/2026-10-22/529900.../*", "doc:sha256:ab12..."],
    "created_at": "2026-10-22T06:14:03Z",
    "status": "draft"
  },
  "claims": [
    {
      "claim_id": "c-0007",
      "text": "Die EBIT-Marge ist seit 2021 jedes Jahr gestiegen.",
      "type": "quantitative",
      "metric_refs": ["ebit_margin@2021..2025"],
      "evidence": [{"doc_hash": "sha256:ab12...", "page": 87, "quote": "..."}],
      "confidence_level": "hoch"
    }
  ],
  "payload": { }
}
```

Der Status durchläuft `draft`, `checked`, `verified`, `rejected`, `escalated`. Nur Claims mit `verified` erreichen den Synthese-Agenten.

### 8.5 Ablauf und Kommunikation

Die Agenten kommunizieren über den Orchestrator und das Dateisystem, nicht direkt miteinander. Das macht jeden Schritt nachvollziehbar und wiederholbar.

```
for kandidat in shortlist (parallel, max 5 gleichzeitig):
    A1 falls Dokumente fehlen
    A2 (2x) falls Werte fehlen        -> J1 vergleicht beide Extraktionen
    P4 Kennzahlen neu berechnen
    A3, A4, A6 parallel
    A5 nach A3 und A4
    J1 rechnet alle zitierten Zahlen blind nach
    J2 prüft jede Behauptung gegen Quelle
    A7 Bear-Fall, dann Erwiderung A3/A5 (max 2 Runden)
    F1 falls Forensik-Flag
    J3 Jury bewertet Gesamtfall
    Status -> verified | escalated | rejected
A9 Bericht
J4 Endkontrolle des Berichts
Dashboard aktualisieren, Benachrichtigung
```

Dateilayout je Lauf.

```
runs/<run_id>/
  manifest.json          Konfigurations-Hashes, Modellversionen, Datenstand
  universe.parquet
  screening.parquet
  candidates/<lei>/
     A3_fundamental.json  A4_qualitative.json  A5_valuation.json
     A6_insider.json      A7_bear.json         rebuttal_1.json
     J1_numbers.json      J2_grounding.json    J3_jury.json
     F1_forensics.json    decision.json
  report.md  report.html
  J4_final_check.json
  log.jsonl              jede Werkzeug- und Modellanfrage mit Zeit, Tokens, Kosten
```

### 8.6 Fehlerbehandlung

| Situation | Reaktion |
|---|---|
| Ausgabe verletzt Schema | bis zu 2 Wiederholungen mit Fehlermeldung im Prompt, dann `escalated` |
| Datenquelle nicht erreichbar | 3 Wiederholungen mit wachsender Pause, dann Kandidat überspringen und im Bericht vermerken |
| Zeitlimit je Kandidat (Default 20 Minuten) | Kandidat `escalated` |
| Kostenbudget je Lauf erreicht (`max_cost_per_run_eur`) | Lauf mit bisherigen Ergebnissen abschließen, Rest vermerken |
| Widerspruch zweier Quellen über 5 Prozent | Kandidat `escalated` mit beiden Werten |
