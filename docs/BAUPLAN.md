# Bauplan

Stand: 12.10.2026. Dieses Dokument beschreibt alle Bauschritte und sagt für jede Datei, die heute nur ein Platzhalter ist, **wann** sie gebaut wird und **was genau** hineinkommt. Verbindlich bleibt die Spezifikation (`docs/spec/`). Der Bauplan ist die Arbeitsliste dazu. Nach jedem Bauschritt werden die erledigten Zeilen hier entfernt und `docs/STATUS.md` aktualisiert.

## Warum 13 Schritte (0 bis 12)?

Jeder Schritt ist so klein, dass er in einem Pull Request prüfbar ist und etwas Sichtbares liefert. Zusammengefasst ergeben die 13 Schritte **5 Bausteine**:

| Baustein | Schritte | Ergebnis für Luca |
|---|---|---|
| A Datenbasis | 0 Gerüst, 1 Universum, 2 Abschlussdaten USA | Aktienliste mit Ländern, dazu geprüfte Abschlusszahlen der US-Firmen |
| B Rechnen und Noten | 3 Kennzahlen, 4 Bewertung, 5 Note und Übersicht | **Erstes nutzbares Ergebnis:** Übersicht aller US-Titel mit Note, Konfidenz und Risiko |
| C Tiefenanalyse | 6 Tiefenanalyse Ende zu Ende | finanzieller Überblick mit 14 Abschnitten für ein Unternehmen, recherchiert von Agenten, gerechnet von Python, geprüft von Prüfagenten |
| D Ausbau | 7 Europa und Rechnungslegung, 8 weitere Scorecards, 9 Insider | dasselbe für europäische Werte, Banken, Versicherer, Immobilien usw., Insider-Signal |
| E Qualität und Bedienung | 10 Prüfer vollständig, 11 Start und Dashboard, 12 Zeitplan (optional) | Jury, Goldstandard, `/stockagent` mit Kategorie-Abfrage, volles Dashboard, auf Wunsch automatische Läufe |

Die Reihenfolge innerhalb eines Bausteins ist fest, weil jeder Schritt auf dem vorigen aufbaut. Luca kann Schritte zusammenlegen, verschieben oder streichen. Schritt 12 ist ausdrücklich optional.

## Die Bauschritte im Einzelnen

### Schritt 0: Gerüst (erledigt, LucaNiklas/Stock-Agent#2)

Projekt mit uv und Python 3.12, CI, Grundtypen (`Money`, `Fact`, `Evidence`, `Claim`, `FreeText`), sechs Gates, CLI-Gerüst, Hooks für Claude Code, Erzeugung der Agent-Dateien.

### Schritt 1: Universum (erledigt, LucaNiklas/Stock-Agent#3)

14.509 Aktien aus den Listen der Deutschen Börse, ISIN-Prüfung, LEI, Hauptsitz und Rechtssitz aus der GLEIF mit Plausibilitätsprüfung, Erkennung von Hinterlegungsscheinen, Lucas Trade-Republic-Prüfungen, Anzeige im Terminal und als HTML (ADR 0001).

### Schritt 2: Abschlussdaten USA

- **Ziel:** Geprüfte Abschlusszahlen der US-Emittenten mit Zeitpunktbezug, dazu Branche (SIC) und Geschäftsadresse der SEC.
- **Entsteht:** SEC-Anbindung, Tabellen `issuers`, `documents`, `facts`, `store.pit_query(as_of=...)`, Datenqualitätsprüfungen aus SPEC 3.2, Zuordnung ISIN zu CIK (Verfahren als ADR 0002 festhalten, weil die SEC keine ISIN liefert).
- **Aufräumen:** `cli.py` in ein Paket `cli/` aufteilen (je Bereich eine Datei), `tests/test_universe.py` in `test_identifiers.py`, `test_sources.py`, `test_universe_update.py` aufteilen.
- **Braucht von Luca:** `SEC_USER_AGENT` in `.env` (Name und E-Mail).
- **Abnahme:** 10 US-Firmen aus dem Universum geladen, Bilanzgleichung erfüllt, Kernwerte gegen den Originalbericht geprüft, SIC-Code und Adresse für alle SEC-Melder im Universum.

### Schritt 3: Formelregister und Kennzahlen

- **Ziel:** Alle Kennzahlen aus SPEC 3.3 bis 3.5, jede schrittweise mit Prüfpunkten (HR-19).
- **Entsteht zuerst:** `src/stockagent/core/calc.py` mit dem Rechenweg (`schritt`, `pruefe`, `ergebnis`) und dem Prüfpunkt-Katalog CP-01 bis CP-08 (SPEC 12.7). Neue Datei, deshalb heute kein Platzhalter.
- **Danach:** Kennzahlen in `config/metrics.yaml` und `core/registry.py`, Trends (SPEC 3.4) in einer neuen Datei `core/trends.py`, Scores in `core/scores.py`. Skill `/add-metric` (schon geschrieben) nutzen.
- **Abnahme:** Jede Kennzahl mit schrittweiser Handrechnung aus einem echten 10-K getestet, Zwischenergebnisse einzeln geprüft. Ein verletzter Prüfpunkt stoppt die Rechnung mit `unknown` und INC-15. Der Rechenweg wird gespeichert.

### Schritt 4: Marktdaten und Bewertung

- **Ziel:** Kurse, Zinsen, Wechselkurse, Reverse-DCF, DCF-Szenarien, Multiples.
- **Neue Datei:** `data/sources/damodaran.py` für Risikoprämie und Branchenbetas als datierter Stand.
- **Braucht von Luca:** Entscheidung zur Kursquelle (SPEC 19 Nr. 1).
- **Abnahme:** Lehrbuchbeispiel exakt reproduziert, höherer WACC ergibt niedrigeren Wert, negativer FCF korrekt behandelt, Rückrechnung CP-06 und Brücke CP-03 in jedem Lauf bestanden.

### Schritt 5: Note und erste Übersicht

- **Ziel:** Erstes nutzbares Ergebnis. Alle US-Titel mit Note, Konfidenz und Risiko in einer Übersicht.
- **Entsteht:** Branchencodes und Kernprodukt, Scorecard Standard, Note, Konfidenz, Risiko, Kategorie, Dashboard, Beobachtungsliste mit `stockagent watch`, Befehle `screen`, `status`, `dashboard`, Tabelle `grade_snapshots` für die Notenkontrolle (SPEC 14.2).
- **Abnahme:** Jeder US-Titel hat eine Note oder Status N mit Grund. Die Notenberechnung läuft über den Rechenweg mit CP-07.

### Schritt 6: Tiefenanalyse Ende zu Ende

- **Ziel:** Finanzieller Überblick mit 14 Abschnitten für ein US-Unternehmen über Lucas Claude-Abo.
- **Entsteht:** Zustandsautomat, Annahme von Agentenausgaben, Werkzeuge, Prompts, Agentenvorlagen in `agents_src/` (A1, A3, A4, A5, A7, A9, J1, J2) mit Modellen aus `config/models.yaml`, Berichtsvorlagen, Skill `/analyze-stock`, Befehl `analyze`. Der `SubagentStop`-Hook ruft `stockagent accept`.
- **Abnahme:** Alle Ausgaben schemakonform, jeder Agent lief mit seinem Modell, ein Schritt außerhalb der Reihenfolge wird abgelehnt, alle 14 Abschnitte vorhanden.

### Schritt 7: Europa, Rechnungslegung, Währung

- **Ziel:** Dasselbe für EU-Werte, vergleichbar über IFRS und US-GAAP.
- **Neue Dateien:** `data/sources/pdf.py` (PDF-Rückfall mit Docling, SPEC 7.4), Agentenvorlage A2 (Extraktion).
- **Abnahme:** 10 DAX-Werte vollständig, je Regel ACC-01 bis ACC-14 ein Test mit echtem Bericht, GBX- und ADR-Fall getestet.

### Schritt 8: Weitere Scorecards

- **Ziel:** Eigene Bewertung für Banken, Versicherer, Immobilien, Versorger, Zykliker, Holdings und Wachstumsfirmen ohne Gewinn (SPEC 3.11).
- **Entsteht:** Erweiterung von `config/scorecards.yaml` und `config/metrics.yaml` um die Kennzahlen dieser Branchen.
- **Abnahme:** Je Scorecard 3 Unternehmen von Hand geprüft.

### Schritt 9: Insider

- **Ziel:** Insider-Signal aus SEC Form 4 und BaFin (SPEC 3.8).
- **Entsteht:** Erweiterung von `data/sources/sec.py` um Form 4, dazu Agentenvorlage A6.
- **Abnahme:** Klassifikation routinemäßig oder opportunistisch für Testpersonen nachvollziehbar korrekt.

### Schritt 10: Prüfer vollständig

- **Ziel:** Jury, Endkontrolle, Forensik, Goldstandard, Test von Gemini als zweiter Modellfamilie.
- **Neue Dateien:** `agents/tools/gemini.py`, `.github/workflows/eval.yml`, Agentenvorlagen J3, J4, F1, ADR zum Gemini-Test.
- **Abnahme:** J1 findet mindestens 95 Prozent der eingebauten Zahlenfehler, J2 mindestens 85 Prozent der erfundenen Aussagen.

### Schritt 11: Start und Dashboard

- **Ziel:** Bequemer Start über `/stockagent` mit Kategorie-Abfrage und volles Dashboard.
- **Entsteht:** Befehl `stockagent run` mit Dialog (`questionary`), Laufplan, alle Ansichten aus SPEC 13.3.
- **Abnahme:** Alle Startwege aus SPEC 9.6 funktionieren, Antworten in `request.json`.

### Schritt 12: Zeitplan (optional)

- **Ziel:** Läufe ohne Luca, etwa wöchentlich.
- **Neue Dateien:** `.github/workflows/scheduled-run.yml` oder ein lokaler Zeitplan in der Claude-Desktop-App, Profil `scheduled` in `config/run_profiles.yaml`, Benachrichtigung.
- **Braucht von Luca:** Entscheidung, ob ein API-Schlüssel mit Kosten pro Token genutzt werden soll (SPEC 19 Nr. 4).
- **Abnahme:** Drei Läufe hintereinander ohne manuellen Eingriff.

## Platzhalter: wann und was

Jede dieser Dateien existiert schon und nennt im Kopf denselben Bauschritt und Inhalt. Ordner mit `/` am Ende enthalten eine `README.md`, weil Git leere Ordner nicht speichert.

| Schritt | Datei | Zweck | Was genau hineinkommt |
|---|---|---|---|
| 2 | `config/concept_map.yaml` | Zuordnung XBRL-Konzept zu interner Größe (SPEC 7.2) | Je interner Größe (`revenue`, `ebit`, `net_income`, `operating_cash_flow`, `capex`, `total_assets`, `equity`, `financial_debt`, `lease_liabilities`, `cash`, `shares_diluted` …) eine Vorrangliste von US-GAAP-Konzepten, etwa `revenue: [us-gaap:Revenues, us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax, us-gaap:SalesRevenueNet]`. In Schritt 7 kommen die ESEF/IFRS-Konzepte dazu |
| 2 | `src/stockagent/core/pit.py` | Zeitpunktbezug (Point-in-Time, SPEC 7.5, HR-07) | Reine Funktionen: aus allen Fassungen eines Werts die zum Analysedatum gültige wählen (`published_at <= as_of`, Restatements erst ab ihrem Datum). Wird von `store.pit_query(as_of=...)` genutzt |
| 2 | `src/stockagent/data/quality.py` | Datenqualitätsprüfungen (SPEC 3.2) | Bilanzgleichung je Periode (Toleranz 0,5 Prozent), XBRL-Summenstruktur, Einheiten und Skalierung, Periodenlogik und TTM ohne Doppelzählung, Abgleich zweier Quellen, Ausreißer über Median und MAD, Restatements erkennen, Aktienanzahl um Splits bereinigen. Ergebnis sind `dq_flags` je Unternehmen, die die Konfidenz bestimmen |
| 2 | `src/stockagent/data/sources/sec.py` | Anbindung SEC EDGAR | Mit `edgartools`: `company_tickers.json` (CIK, Ticker), Submissions (Name, SIC-Code, Geschäftsadresse, Gründungsstaat, Liste der Einreichungen), Company Facts (XBRL-Werte mit Konzept, Periode, Einheit, Einreichungsdatum). User-Agent aus `SEC_USER_AGENT` in `.env`, höchstens 10 Anfragen je Sekunde, Rohdaten über `rawstore`. In Schritt 9 kommt Form 4 (Insider) dazu |
| 2 | `tests/fixtures/` | Kleine Beispieldaten für Tests | Ausschnitte echter SEC-Antworten (Company Facts, Submissions) für 2 bis 3 Firmen, damit Tests ohne Internet laufen. Je Datei Quelle und Abrufdatum im Kopf |
| 3 | `src/stockagent/core/scores.py` | Qualitäts- und Risiko-Scores (SPEC 3.5) | Piotroski F-Score (9 Signale), Altman Z und Z'' (Produzenten und Nicht-Produzenten), Beneish M-Score (8 Variablen), Sloan-Accruals, Qualitätskomposit nach Asness, Frazzini, Pedersen. Jeder Score über den Rechenweg aus `core/calc.py` mit Prüfpunkten CP-01, CP-02, CP-07 (HR-19) |
| 3 | `tests/metrics/` | Ein Test je Kennzahl | Je Kennzahl eine Datei `test_<id>.py` mit schrittweiser Handrechnung aus einem echten 10-K: jedes Zwischenergebnis einzeln geprüft, Quelle (Dokument, Seite) im Kommentar, dazu ein Fall mit verletztem Prüfpunkt |
| 4 | `src/stockagent/core/fx.py` | Währungsregeln (SPEC 5.2) | Reine Funktionen: Bilanzposten zum Stichtagskurs, GuV und Cashflow zum Periodendurchschnitt, Unterwährungen (GBX, ZAc, ILA), ADR-Verhältnis, Fisher-Umrechnung von Diskontsätzen, Plausibilitätsprüfung INC-13. Über den Rechenweg mit CP-01 und CP-02 |
| 4 | `src/stockagent/core/valuation.py` | Bewertung (SPEC 3.6) | Reverse-DCF (auf FCF- und Umsatzbasis), DCF in drei Szenarien mit Annahmestufen aus der Historie, Multiples gegen Historie und Vergleichsgruppe, Sensitivitätsmatrix, Unternehmenswert-Brücke, deterministische Bewertungsbedingung. Prüfpunkte CP-03 (Brücke) und CP-06 (Rückrechnung) in jedem Lauf |
| 4 | `src/stockagent/data/sources/fx.py` | Wechselkurse (SPEC 5.2) | EZB-Referenzkurse über die SDMX-API, täglich, mit Datum und Quelle. Daraus Stichtags- und Durchschnittskurse |
| 4 | `src/stockagent/data/sources/prices.py` | Kurse und Handelsvolumen (SPEC 7.3) | Tägliche Schlusskurse und Volumen je ISIN mit Währung und Quelle. Quelle offen (SPEC 19 Nr. 1): offizielle kostenlose Quelle, falls vorhanden, sonst Datenanbieter nach Lucas Entscheidung. `yfinance` nur für die Entwicklung |
| 4 | `src/stockagent/data/sources/rates.py` | Risikofreie Zinsen (SPEC 3.6, 7.3) | 10-jährige Bundesanleihe (Bundesbank-Zinsstrukturkurve) und 10-jährige US-Treasury (FRED), jeweils mit Datum. Grundlage für WACC und Endwachstum |
| 5 | `config/scorecards.yaml` | Scorecard-Zuordnung (SPEC 3.11) | In Schritt 5 nur `standard` mit ihren Kennzahlen je Säule. Regeln für die Zuordnung über SIC, NACE und Kennzahlen. Weitere Scorecards in Schritt 8 |
| 5 | `config/scoring.yaml` | Gewichte und Schwellen der Bewertungsskala (SPEC 6) | Säulengewichte (Qualität 25, Bewertung 25, Stabilität 15, Wachstum 15, Kapitalallokation 10, Insider 10 Prozent), Kappungsgrenzen, Notenschwellen A bis E, Bedingungen für K1 bis K4 und R1 bis R5, Kategorien, Hysterese, Mindestgröße der Vergleichsgruppe (15), `min_discount_to_multiples`, Überprüfungskriterium der Notenkontrolle |
| 5 | `config/sectors.yaml` | Branchenliste und Abbildung (SPEC 7.8, 9.7) | 11 Hauptbranchen mit Unterbranchen und deutscher Bezeichnung, Abbildung SIC- und NACE-Bereiche auf diese Branchen, Abbildung Wikidata-Branchen auf NACE |
| 5 | `src/stockagent/core/decisions.py` | Kategorie und Zustandsautomat (SPEC 6.5, HR-13) | Deterministische Kategorie (Attraktiv, Beobachten, Neutral, Unattraktiv, Eskaliert, Nicht bewertbar), Hysterese über zwei Läufe (9.5). Sprachmodelle haben nur die Übergänge `downgrade` und `escalate` |
| 5 | `src/stockagent/core/grading.py` | Note, Konfidenz, Risikoklasse (SPEC 6) | Perzentile je Kennzahl in der Vergleichsgruppe mit stufenweiser Erweiterung, Säulenwerte, Gesamtwert, Kappungen, Note A bis E oder N, Konfidenz K1 bis K4, Risikoklasse R1 bis R5. Über den Rechenweg mit CP-07 |
| 5 | `src/stockagent/dashboard/__init__.py` | Paket Dashboard | Paketkennung, keine Logik |
| 5 | `src/stockagent/dashboard/build.py` | Dashboard bauen (SPEC 13.3) | Schreibt eine einzelne HTML-Datei mit eingebetteten Daten. Ansicht Übersicht (alle Unternehmen mit Note, Konfidenz, Risiko, Branche, Land, filterbar) und Unternehmensseite mit Notenzerlegung. Weitere Ansichten in Schritt 11 |
| 5 | `src/stockagent/dashboard/template.html` | HTML-Vorlage des Dashboards | Seitengerüst mit Filtern, Tabelle, Hell- und Dunkelmodus, Notenzerlegung. Baut auf `report/templates/universe.html` auf |
| 5 | `src/stockagent/data/sources/sectors.py` | Branchencodes (SPEC 7.8) | Reihenfolge: SIC aus den SEC-Submissions, ggf. Datenanbieter, Wikidata (Eigenschaft Branche, über ISIN oder LEI), sonst Vorschlag von A0 mit Lucas Bestätigung. Quelle und Datum je Code, unsichere Zuordnung senkt die Konfidenz. Auch Kurzbeschreibung des Kernprodukts, soweit die Quelle sie liefert |
| 5 | `state/watchlist.yaml` | Lucas Beobachtungsliste (SPEC 9.7) | Liste von ISINs, gepflegt mit `stockagent watch add|remove <ISIN>`. Titel der Liste gehen bei Läufen immer in die Tiefenanalyse |
| 6 | `.claude/skills/analyze-stock/SKILL.md` | Skill /analyze-stock | Nimmt ISIN oder Name, löst auf ISIN und LEI auf, startet `stockagent analyze`, führt die Agenten in der Reihenfolge aus, die `stockagent next` vorgibt, und öffnet am Ende den finanziellen Überblick |
| 6 | `schemas/json/` | Exportierte JSON-Schemas | Aus den Pydantic-Modellen erzeugte Schemas je Agentenausgabe (`a3_output.json`, `j1_output.json` …). Die Agent-Prompts verweisen darauf |
| 6 | `src/stockagent/agents/prompts/` | Versionierte Prompts je Agent | Je Agent eine Prompt-Datei mit Version. Jede Änderung braucht einen Eval-Lauf (CLAUDE.md, SPEC 11.6) |
| 6 | `src/stockagent/agents/runner.py` | Annahme von Agentenausgaben | Prüft jede Ausgabe gegen ihr Schema und alle Gates in fester Reihenfolge (SPEC 12.6), schickt Abgelehnte höchstens zweimal mit Fehlermeldung zurück, dann `escalated`. Protokolliert Modell, Dauer und Tokens in `log.jsonl` |
| 6 | `src/stockagent/agents/tools/__init__.py` | Werkzeuge für Agenten | Skripte, die Agenten aufrufen dürfen: `query_facts`, `compute_metric` (liefert den Rechenweg mit), `query_metrics`, `search_descriptions`, `fetch_document`, `run_dcf`, `run_reverse_dcf`, `peer_multiples`. In Schritt 7 `parse_pdf`, in Schritt 10 `gemini` |
| 6 | `src/stockagent/judges/__init__.py` | Paket Prüfagenten | Paketkennung, keine Logik |
| 6 | `src/stockagent/judges/grounding.py` | Auswertung J2 Belegprüfer (SPEC 11.2) | Sammelt je Claim `supported`, `partially`, `not_supported`, `contradicted`, streicht unbelegte Aussagen, eskaliert bei `contradicted` |
| 6 | `src/stockagent/judges/numbers.py` | Auswertung J1 Zahlenprüfer (SPEC 11.2) | Vergleicht J1-Ergebnisse mit den Werten der Agenten erst nach J1s Rechnung: Toleranz 0,5 Prozent `match`, bis 2 Prozent `rounding`, darüber `mismatch`. Ein `mismatch` bei einer Kernkennzahl eskaliert |
| 6 | `src/stockagent/orchestrator.py` | Zustandsautomat der Tiefenanalyse (SPEC 15.1) | `stockagent next <run_id>` nennt den nächsten erlaubten Schritt (welcher Agent, welche Eingabedatei, wohin die Ausgabe), `stockagent accept <run_id> <datei>` nimmt eine Ausgabe an. Erzwingt Reihenfolge, Blindheit von J1 (HR-14) und Grenzen (HR-18), kann abgebrochene Läufe fortsetzen |
| 6 | `src/stockagent/report/render.py` | Bericht erzeugen (SPEC 12.3) | Baut aus dem Pydantic-Objekt `AnalysisReport` über Jinja2 den finanziellen Überblick mit 14 Abschnitten, setzt die Platzhalter aus HR-01 mit formatierten Werten ein, deutsches Zahlenformat |
| 6 | `src/stockagent/report/templates/analysis.html.j2` | Vorlage Analyse als HTML | Dieselben 14 Abschnitte als Seite. Jede Zahl führt per Klick zum Rechenweg und zur Quelle (SPEC 13.1) |
| 6 | `src/stockagent/report/templates/analysis.md.j2` | Vorlage Analyse als Markdown | Die 14 Pflichtabschnitte aus SPEC 12.3 in fester Reihenfolge: Kopf, Urteil, These, Geschäftsmodell, Kennzahlentabelle, Ertragsqualität, Bewertung, Anpassungen, Insider, Qualitative Befunde, Gegenposition, Ungereimtheiten, Prüfprotokoll, Grenzen und Quellen |
| 6 | `tests/recorded/` | Aufgezeichnete Modellantworten | Echte Agentenantworten zu festen Testdaten. Damit laufen Snapshot-Tests der Berichte ohne Modellaufrufe und bitgleich (SPEC 12.5) |
| 7 | `config/accounting_adjustments.yaml` | Normalisierungsregeln (SPEC 4.3) | Je Regel ACC-01 bis ACC-14: ID, Version, Thema, Quelle, Parameter |
| 7 | `config/hyperinflation.yaml` | Hochinflationsländer nach IAS 29 (SPEC 5.2 Nr. 8) | Länderliste mit Gültigkeitszeitraum und Quelle. Betroffene Unternehmen erhalten Flag `hyperinflation` und höchstens K3 |
| 7 | `config/withholding_tax.yaml` | Quellensteuer auf Dividenden (SPEC 5.2 Nr. 12) | Satz je Land mit Quelle und Datum. Nur Information im Bericht, keine Steuerrechnung (Steuer ist außerhalb des Umfangs) |
| 7 | `src/stockagent/core/accounting.py` | Normalisierung der Rechnungslegung (SPEC 4.3) | Regeln ACC-01 bis ACC-14 (Leasing, Entwicklungskosten, LIFO, Zinsen im Cashflow, IFRS 18, Pensionen …). Jede angewandte Anpassung mit Betrag im Bericht. Nach jeder Anpassung Summenprobe CP-03 |
| 7 | `src/stockagent/data/sources/esef.py` | EU-Abschlussdaten (SPEC 7.2) | ESEF-Inline-XBRL über filings.xbrl.org (`xbrl-filings-api`), Abdeckung ab Geschäftsjahr 2020. Anhangangaben fehlen meist strukturiert, dafür der PDF-Rückfall (SPEC 7.4) mit A2 |
| 9 | `config/insider_thresholds.yaml` | Meldeschwellen je Land (SPEC 3.8 Nr. 9) | Schwelle in EUR je Land mit Gültigkeit ab Datum und Quelle (Deutschland 50.000 EUR ab 2026, EU-Standard 20.000 EUR) |
| 9 | `src/stockagent/core/insider.py` | Insider-Signal (SPEC 3.8) | Nur Käufe am offenen Markt, routinemäßig gegen opportunistisch (Cohen, Malloy, Pomorski), Cluster, Rollengewicht, Abklingen mit 90 Tagen Halbwertszeit, Höchstgewicht 15 Prozent |
| 9 | `src/stockagent/data/sources/bafin.py` | Insidergeschäfte Deutschland (SPEC 7.3) | BaFin-Datenbank Geschäfte von Führungskräften, höflich mit Pausen und Cache, robots.txt beachten. Meldeschwelle 50.000 EUR seit 2026 beachten |
| 10 | `.claude/skills/review-escalations/SKILL.md` | Skill /review-escalations | Geht eskalierte Fälle einzeln mit Luca durch: Streitpunkte, beide Werte mit Quellen, Lucas Entscheidung wird in `decisions` und im Goldstandard gespeichert |
| 10 | `eval/gold/` | Goldstandard | Zunächst 5 Unternehmen mit von Luca geprüften Kernkennzahlen und absichtlich fehlerhaften Analysen (falsche Zahl, falsche Periode, erfundene Aussage, eingebettete Anweisung). Dateien sind per Hook schreibgeschützt |
| 10 | `eval/run_eval.py` | Goldstandard-Lauf (SPEC 11.6) | Lässt die Prüfer gegen `eval/gold/` laufen und misst Fangquote je Fehlerart, Fehlalarme, Übereinstimmung mit Luca (Cohens Kappa). Mindestwerte: J1 95 Prozent, J2 85 Prozent |
| 10 | `src/stockagent/judges/final_check.py` | J4 Endkontrolle (SPEC 11.2) | Prüft den fertigen Bericht: Zahlen gleich `decision.json`, Belege je Absatz, keine Kaufaufforderung, Gegenposition vollständig |
| 10 | `src/stockagent/judges/jury.py` | J3 Jury (SPEC 11.2, 11.3) | Drei Richter (Opus, Sonnet, Gemini oder Haiku), Rubrik mit sechs Kriterien, Median je Kriterium, Uneinigkeit bei Spannweite über 2, Reihenfolge Bull/Bear in der Hälfte vertauscht |
| 11 | `.claude/skills/stockagent/SKILL.md` | Skill /stockagent | Kategorie-Abfrage in zwei Runden mit AskUserQuestion (SPEC 9.7), Laufplan zeigen, nach Bestätigung `stockagent run` starten, Fortschritt melden, Ergebnis zusammenfassen, Dashboard öffnen |
| 11 | `config/run_profiles.yaml` | Laufprofile (SPEC 9.6, 9.7) | Profile für `stockagent run --profile`: Kategorie, Größenklassen, Tiefe, Höchstzahl Tiefenanalysen. In Schritt 12 das Profil `scheduled` |

## Neue Dateien ohne heutigen Platzhalter

| Schritt | Datei | Inhalt |
|---|---|---|
| 2 | `docs/adr/0002-isin-cik.md` | Wie ISIN und CIK der SEC zugeordnet werden |
| 2 | `src/stockagent/cli/` (Paket) | Aufteilung der heutigen `cli.py` je Bereich |
| 3 | `src/stockagent/core/calc.py` | Rechenweg mit Prüfpunkten (HR-19, SPEC 12.7) |
| 3 | `src/stockagent/core/trends.py` | Trends und Zeitreihen (SPEC 3.4): Theil-Sen-Steigung, CAGR, Stabilität |
| 4 | `src/stockagent/data/sources/damodaran.py` | Risikoprämie, Branchenbetas und -multiples als datierter Stand |
| 6 | `agents_src/<agent>.md` | Vorlagen A1, A3, A4, A5, A7, A9, J1, J2 mit Pflicht-Präambel |
| 7 | `src/stockagent/data/sources/pdf.py` | PDF-Rückfall mit Docling (SPEC 7.4) |
| 10 | `src/stockagent/agents/tools/gemini.py` | Gemini CLI als externer Prüfer (SPEC 8.8) |
| 10 | `.github/workflows/eval.yml` | Goldstandard-Lauf bei Änderungen an Prompts, Agenten oder Konfiguration |
| 12 | `.github/workflows/scheduled-run.yml` | Zeitplan, nur bei API-Betrieb |

## Bewusst behalten, obwohl fast leer

- `docs/spec/10-bestandspruefung-und-verkaufslogik.md` und Abschnitt 3.10: nur ein Verweis auf Anhang A. Sie bleiben, damit die Abschnittsnummern stimmen, auf die andere Stellen der Spezifikation verweisen.
