## 7. Datenquellen und Datenschicht

### 7.1 Handelsuniversum: bei Trade Republic handelbare Aktien

Ziel ist die Liste aller Aktien, die bei Trade Republic gekauft werden können. Trade Republic bietet keine offizielle API, veröffentlicht aber eine öffentliche Produktübersicht ohne Login: **https://app.traderepublic.com/browse/stock**. Sie zeigte am 09.10.2026 11.197 Aktien mit Name und ISIN, filterbar nach Sektoren, Ländern und Indizes. Diese Seite ist die Primärquelle.

| Schritt | Vorgehen |
|---|---|
| 1. Abrufweg klären | Erster Bauschritt (16.10, Schritt 1). Claude Code untersucht, wie die Seite ihre Liste lädt (die Tabelle wird nachgeladen), prüft robots.txt und Nutzungsbedingungen und dokumentiert Abrufweg und Grenzen in `docs/adr/0001-universum-quelle.md`. Bevorzugt wird ein öffentlicher Datenendpunkt der Seite ohne Login, sonst das Auslesen der gerenderten Seite. Ein Login oder das private Protokoll der App wird nie verwendet (HR-09) |
| 2. Rohliste laden | Modul `data/sources/universe_tr.py` nach 18.2. Jede Rohdatei landet unverändert in `data/raw/` mit Hash, Abrufdatum und URL. Abruf höflich mit Pausen und Caching, höchstens einmal pro Woche vollständig. Mitgeliefert werden, soweit vorhanden, Sektor, Land und Indexzugehörigkeit als Zusatzinformation |
| 3. Kennungen | ISIN, LEI (GLEIF-API, kostenlos), Ticker, CIK bei US-Emittenten (SEC `company_tickers.json`) |
| 4. Zusammenführung | Mehrfachlistings auf LEI, Primärnotierung am Heimatmarkt als Kursquelle |
| 5. Handelbarkeitsstatus | Je Titel `tr_status` mit Quelle und Datum: `bestaetigt` (in der aktuellen Liste von app.traderepublic.com/browse/stock), `entfernt` (war gelistet, fehlt in der aktuellen Liste), `unbekannt` (nur aus anderen Quellen bekannt). Die Übersicht zeigt standardmäßig nur `bestaetigt` und zeigt den Status immer an |

Häufigkeit: wöchentlich. Ändert sich die Liste um mehr als 5 Prozent zur Vorwoche, prüft das System die Quelle auf einen Formatwechsel, bevor es die neue Liste übernimmt.

Ist die Seite nicht erreichbar oder ändert sich ihr Aufbau, bleibt die letzte gültige Liste mit ihrem Datum in Kraft und der Bericht weist darauf hin (HR-16). Rückfall-Quellen nur zum Abgleich: Instrumentenlisten von LS Exchange, Xetra, Börse Frankfurt und Tradegate.

Inoffizielle Bibliotheken, die das private Protokoll von Trade Republic nutzen (etwa `pytr`), sind nicht vorgesehen. Sie brauchen einen Login und verstoßen gegen HR-09.

Das Universum umfasst rund 11.000 Aktien (Stand 09.10.2026). Alle erhalten bei jedem Lauf eine quantitative Note ohne Modellaufrufe, soweit Daten vorliegen. Für US-Emittenten und EU-Emittenten an regulierten Märkten liegen strukturierte Abschlussdaten kostenlos vor. Für die übrigen Unternehmen (Freiverkehr, Asien, Schwellenländer) fehlen kostenlose strukturierte Daten. Sie erhalten Status N mit Grund "keine strukturierten Daten", bis Luca einen Datenanbieter freigibt (19, Nr. 1).

### 7.2 Abschlussdaten

| Region | Primärquelle | Format | Kosten | Hinweise |
|---|---|---|---|---|
| USA | SEC EDGAR, `data.sec.gov` (Company Facts, Company Concept, Frames, Submissions) | JSON mit US-GAAP-XBRL-Konzepten | kostenlos | Pflicht-Header `User-Agent` mit Name und E-Mail, höchstens 10 Anfragen pro Sekunde. Bibliothek `edgartools` nutzen |
| EU, regulierte Märkte | ESEF-Inline-XBRL über `filings.xbrl.org` (XBRL International), Python-Paket `xbrl-filings-api` | xBRL-JSON, Bericht als XHTML | kostenlos | Abdeckung ab Geschäftsjahr 2020, nicht vollständig. Freiverkehrswerte fehlen, weil dort keine ESEF-Pflicht gilt. Im Anhang ist nur Block-Tagging Pflicht, deshalb fehlen Angaben wie Leasingaufwand, LIFO, aktienbasierte Vergütung und Segmente meist strukturiert. Für EU-Werte ist der PDF-Rückfall (7.4) der Normalfall für Anhangangaben |
| EU, Rückfall | Unternehmensregister und Investor-Relations-Seiten | PDF | kostenlos | Extraktion nach Abschnitt 7.4 |
| EU, mittelfristig | ESAP (European Single Access Point), Aufbau läuft | | | Bei Verfügbarkeit als Primärquelle einbinden |
| Querprüfung (optional) | Ein kommerzieller Anbieter, zum Beispiel Financial Modeling Prep, EODHD oder financialreports.eu | REST-JSON | ab rund 20 bis 50 EUR pro Monat | Nur nach Entscheidung 19 Nr. 1. Ohne Anbieter prüft die Datenqualitätsprüfung 5 XBRL-Werte gegen den Originalbericht (Stichprobe) und vermerkt die fehlende zweite Quelle in der Konfidenz |

ESEF-Taxonomie und US-GAAP-Taxonomie haben unterschiedliche Konzeptnamen. Das Mapping auf die internen Kennzahl-Eingaben steht in `config/concept_map.yaml` mit Vorrangreihenfolge je interner Größe. Fehlt ein Konzept, sucht der Extraktionsagent im Bericht und kennzeichnet den Wert als `source_type: pdf_extracted`.

### 7.3 Markt- und Zusatzdaten

| Daten | Quelle | Hinweise |
|---|---|---|
| Kurse und Volumen (täglich) | offizielle kostenlose Quelle, falls vorhanden (in Schritt 4 recherchieren), sonst Anbieter nach 19 Nr. 1. `yfinance` nur für Entwicklung | `yfinance` ist inoffiziell und für den Dauerbetrieb ungeeignet |
| Wechselkurse | EZB-Referenzkurse (SDMX-API) | alle Vergleiche in EUR, Originalwährung immer mitspeichern |
| Risikofreier Zins | Bundesbank-Zinsstrukturkurve, US-Treasury (FRED) | |
| Aktienrisikoprämie, Branchenbetas, Branchenmultiples | Damodaran-Datensätze (NYU Stern, jährlich und monatlich) | als datierter Snapshot speichern |
| Insider Deutschland | BaFin-Datenbank "Geschäfte von Führungskräften" plus Veröffentlichungen der Emittenten | BaFin bietet keine offizielle API. Abruf höflich mit Pausen und Caching, robots.txt beachten. Alternativ kommerzieller Insider-Feed |
| Insider USA | SEC Form 4 (XML) über EDGAR | strukturiert, Transaktionscodes direkt nutzbar |
| Insider übrige EU | Seiten der nationalen Aufsichten | v2 |
| ETF-Bestände | Positionsdateien der ETF-Emittenten | für Durchschau-Gewichte |
| Nachrichten | nur über Websuche des Agenten mit Quellen-URL | nie als Zahlenquelle |

### 7.4 PDF-Extraktion (nur Rückfall)

1. Parser in dieser Reihenfolge. Docling (Open Source, lokal) zuerst, bei schlechter Tabellenqualität LlamaParse. Beide liefern Seitenzahlen und Tabellenstruktur.
2. Der Extraktionsagent bekommt die relevanten Seiten vollständig in den Kontext, statt Schnipsel aus einer Vektorsuche. Die FinanceBench-Ergebnisse sprechen klar für langen Kontext statt Retrieval.
3. Jeder extrahierte Wert speichert Dokument-Hash, Seite, Tabellenüberschrift, Zeilen- und Spaltenbeschriftung, Einheit, Skalierung und den Originaltext der Zelle.
4. Zwei unabhängige Extraktionen (unterschiedliche Prompts, idealerweise unterschiedliche Modelle). Weichen sie ab, entscheidet der Zahlenprüfer anhand der Seite.
5. Extrahierte Werte durchlaufen dieselben Datenqualitätsprüfungen wie XBRL-Werte.

### 7.5 Zeitpunktbezug (Point-in-Time)

Jeder Datensatz hat drei Zeitstempel.

| Feld | Bedeutung |
|---|---|
| `period_end` | Stichtag, auf den sich der Wert bezieht |
| `published_at` | Zeitpunkt der öffentlichen Verfügbarkeit (Einreichungsdatum, Meldedatum) |
| `retrieved_at` | Abrufzeitpunkt durch das System |

Jede Abfrage für eine Analyse zum Zeitpunkt T filtert auf `published_at <= T`. Bei Restatements gelten bis zum Restatement-Datum die alten Werte. Das ist Voraussetzung für jeden ehrlichen Backtest.

### 7.6 Speicherung

| Ebene | Technik | Inhalt |
|---|---|---|
| Rohdaten | Dateisystem `data/raw/`, Name ist SHA-256 des Inhalts | Originale aller Berichte, JSON-Antworten, Positionsdateien. Unveränderlich |
| Strukturierte Daten | DuckDB (eine Datei, schnelle Analysen) | Tabellen aus Abschnitt 7.7 |
| Lauf-Artefakte | `runs/<run_id>/` | alle Agenten-Ein- und Ausgaben als JSON, Berichte, Diagramme |
| Code und Konfiguration | Git | jede Konfigurationsänderung ist ein Commit |

DuckDB reicht für das Datenvolumen eines Privatanlegers völlig. Ein Wechsel auf PostgreSQL ist nur nötig, wenn mehrere Prozesse gleichzeitig schreiben.

### 7.7 Datenmodell (Kern)

```
issuers(lei PK, name, country, sector_sic, sector_nace, accounting_standard, fiscal_year_end)
listings(isin PK, lei FK, ticker, exchange_mic, currency, is_primary, tr_status[bestaetigt|entfernt|unbekannt],
         tr_source, tr_checked_at)
documents(doc_hash PK, lei FK, doc_type, period_end, published_at, retrieved_at, source_url, language, pages)
facts(fact_id PK, lei FK, concept, internal_metric, value, unit, scale, currency, period_start, period_end,
      published_at, source_type[xbrl|pdf_extracted|vendor], doc_hash FK, page, xbrl_context, extraction_run_id,
      superseded_by)
prices(isin, date, close, volume, currency, source)
metrics(run_id, lei, metric_id, metric_version, period_end, value, inputs_json, computed_at)
insider_tx(tx_id PK, lei, person_name, role, relation[self|spouse|child|household|controlled_entity],
           tx_type[buy|sell|grant|exercise|tax|gift|other], open_market bool, plan_10b5_1 bool,
           shares, price, currency, value_eur, trade_date, published_at, source_doc_hash, routine_class)
scores(run_id, lei, component, value, percentile, peer_group, methodology_version)
valuations(run_id, lei, method, scenario, assumptions_json, value_per_share, implied_growth, sensitivity_json)
flags(run_id, lei, flag_id, severity, evidence_json)
judgments(run_id, lei, judge_id, model, check_type, verdict, confidence, rationale, evidence_json, blind bool)
decisions(run_id, lei, category, score_total, status, human_decision, human_note)
grade_snapshots(date, lei, grade, confidence, risk, score_total, methodology_version, price_eur)
```

### 7.8 Branchencodes

Vergleichsgruppen und Scorecards brauchen für jedes Unternehmen einen Branchencode. GICS ist lizenzpflichtig, GLEIF liefert keine Branchencodes. Reihenfolge der Quellen:

1. SIC aus den SEC-Submissions für US-Emittenten und ausländische SEC-Melder.
2. Kommerzieller Anbieter, falls nach 19 Nr. 1 vorhanden.
3. Wikidata (Eigenschaft "Branche", über ISIN oder LEI gefunden), abgebildet auf NACE über `config/sectors.yaml`.
4. Fehlt alles, schlägt der Kategorie-Agent A0 eine Branche mit Belegstelle aus der Geschäftsbeschreibung vor. Wirksam wird sie erst nach Lucas Bestätigung. Bis dahin hat das Unternehmen Status N mit Grund "Branche unbekannt".

Quelle und Datum des Codes stehen an jedem Unternehmen. Eine unsichere Zuordnung (Quellen 3 und 4) senkt die Konfidenz um eine Stufe.
