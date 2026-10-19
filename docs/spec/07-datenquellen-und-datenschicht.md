## 7. Datenquellen und Datenschicht

### 7.1 Handelsuniversum

Ziel sind die Aktien, die bei Trade Republic gekauft werden können. Trade Republic bietet dafür keinen automatisierbaren Zugang: Die Produktübersicht unter app.traderepublic.com/browse/stock lädt ihre Liste über eine durch AWS WAF geschützte Schnittstelle, und ein Umgehen des Bot-Schutzes ist ausgeschlossen. Details und Befunde stehen in `docs/adr/0001-universum-quelle.md`.

| Schritt | Vorgehen |
|---|---|
| 1. Basisliste | "All tradable instruments"-Dateien der Deutschen Börse für Börse Frankfurt und Xetra, nur Stammaktien (`CS`). Die Datei-Links werden auf den Downloadseiten aus `config/sources.yaml` gesucht. Modul `data/sources/deutsche_boerse.py` |
| 2. Rohdaten | Jede Datei unverändert unter `data/raw/` (SHA-256, gzip) mit Abrufzeit und URL (`data/rawstore.py`) |
| 3. Kennungen | ISIN mit Prüfziffer (`core/identifiers.py`), WKN, Kürzel, LEI aus der ISIN-LEI-Datei der GLEIF (`data/sources/gleif.py`). Mehrdeutige LEI bleibt leer |
| 3a. Länder | Über die GLEIF-API je LEI Hauptsitz und Rechtssitz (Rechtsordnung). Genutzt nur, wenn der Börsenname zu einem LEI-Namen passt und bei normalen Aktien ISIN-Land und Rechtssitz zusammenpassen. Herkunft je Titel: `gleif`, `isin` (unsicher) oder `konflikt` (ADR 0001) |
| 3b. Art | Hinterlegungsscheine (ADR, GDR, CDR, CDI, SDR, NY-Shares) am Börsennamen erkannt |
| 4. Speicherung | Tabelle `listings` in DuckDB, eine Zeile je ISIN. Fehlt ein Titel in einer neuen Liste, bleibt er mit `listed = false` erhalten |
| 5. Handelbarkeit bei Trade Republic | Luca prüft in der App und hält es fest: `stockagent tr-check <ISIN> ja|nein` (`state/tr_checks.yaml`). Status `bestaetigt`, `nicht_handelbar`, ohne Eintrag `ungeprueft` |
| 6. Anzeige | `stockagent universe show` im Terminal, `stockagent universe html` als durchsuchbare Seite unter `data/views/universum.html` |

Häufigkeit: höchstens wöchentlich (`min_refresh_days`). Ändert sich die Anzahl um mehr als 5 Prozent zur letzten Liste, übernimmt das System die neue Liste nur mit `--force`, damit ein Formatwechsel der Quelle nicht unbemerkt Titel löscht.

Das Universum umfasst rund 14.500 Aktien (Stand 12.10.2026) und ist damit größer als das von Trade Republic (11.197 am 09.10.2026). Alle erhalten eine quantitative Note ohne Modellaufrufe, soweit Daten vorliegen. Für US-Emittenten und EU-Emittenten an regulierten Märkten liegen strukturierte Abschlussdaten kostenlos vor. Für die übrigen (Freiverkehr, Asien, Schwellenländer) fehlen kostenlose strukturierte Daten. Sie erhalten Status N mit Grund "keine strukturierten Daten", bis Luca einen Datenanbieter freigibt (19, Nr. 1).

Inoffizielle Bibliotheken, die das private Protokoll von Trade Republic nutzen (etwa `pytr`), sind nicht vorgesehen (HR-09).

### 7.2 Abschlussdaten

| Region | Primärquelle | Format | Kosten | Hinweise |
|---|---|---|---|---|
| USA | SEC EDGAR, `data.sec.gov` (Company Facts, Submissions) und das XBRL des Originalberichts unter `www.sec.gov/Archives` | JSON mit US-GAAP-XBRL-Konzepten | kostenlos | Pflicht-Header `User-Agent` mit Name und E-Mail, höchstens 10 Anfragen pro Sekunde. Zuordnung ISIN zu CIK über OpenFIGI und die Tickerliste der SEC (ADR 0002). Welche Information aus welcher Quelle kommt, steht in der Quellenkarte (8.9) |
| EU, regulierte Märkte | ESEF-Inline-XBRL über `filings.xbrl.org` (XBRL International), Python-Paket `xbrl-filings-api` | xBRL-JSON, Bericht als XHTML | kostenlos | Abdeckung ab Geschäftsjahr 2020, nicht vollständig. Freiverkehrswerte fehlen, weil dort keine ESEF-Pflicht gilt. Im Anhang ist nur Block-Tagging Pflicht, deshalb fehlen Angaben wie Leasingaufwand, LIFO, aktienbasierte Vergütung und Segmente meist strukturiert. Für EU-Werte ist der PDF-Rückfall (7.4) der Normalfall für Anhangangaben |
| EU, Rückfall | Unternehmensregister und Investor-Relations-Seiten | PDF | kostenlos | Extraktion nach Abschnitt 7.4 |
| EU, mittelfristig | ESAP (European Single Access Point), Aufbau läuft | | | Bei Verfügbarkeit als Primärquelle einbinden |
| Querprüfung (optional) | Ein kommerzieller Anbieter, zum Beispiel Financial Modeling Prep, EODHD oder financialreports.eu | REST-JSON | ab rund 20 bis 50 EUR pro Monat | Nur nach Entscheidung 19 Nr. 1. Ohne Anbieter prüft die Datenqualitätsprüfung 5 XBRL-Werte gegen den Originalbericht (Stichprobe) und vermerkt die fehlende zweite Quelle in der Konfidenz |

ESEF-Taxonomie und US-GAAP-Taxonomie haben unterschiedliche Konzeptnamen. Das Mapping auf die internen Kennzahl-Eingaben steht in `config/concept_map.yaml` mit Vorrangreihenfolge je interner Größe. Fehlt ein Konzept, sucht der Extraktionsagent im Bericht und kennzeichnet den Wert als `source_type: pdf_extracted`.

### 7.3 Markt- und Zusatzdaten

| Daten | Quelle | Hinweise |
|---|---|---|
| Kurse, Volumen, Splits, Dividenden (täglich) | Yahoo Finance über die Chart-Adresse, eigenes Modul `data/sources/yahoo.py`, Symbol über OpenFIGI (ADR 0005) | inoffiziell, nur persönliche Nutzung, nur angefragte Titel und Vergleichsgruppe, abschaltbar. Polygon als zweite Quelle für US-Kurse vorgesehen |
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

Für SEC-Werte ist `published_at` der Annahmezeitpunkt der SEC (`acceptanceDateTime`). Fehlt er, gilt das Ende des Einreichungstags in New York, damit ein Wert nie früher als bekannt erscheint. Wiederholt ein späterer Bericht einen Wert nur gröber gerundet (etwa 96,7 Mrd. statt 96.662 Mio.), ist das kein Restatement: Die genauere Fassung bleibt maßgeblich (`core/pit.py`, mindestens drei gültige Ziffern). Übernommen werden nur Werte aus Abschlussberichten (10-K, 10-Q, 20-F, 40-F, 6-K und Korrekturen), nicht aus Proxy-Erklärungen oder 8-K (`sec.report_forms`).

### 7.6 Speicherung

| Ebene | Technik | Inhalt |
|---|---|---|
| Rohdaten | Dateisystem `data/raw/`, Name ist SHA-256 des Inhalts | Originale aller Berichte, JSON-Antworten, Positionsdateien. Unveränderlich. Einzige Ausnahme: GLEIF-Hilfsdaten ohne Finanzwerte werden nur für die letzten `gleif.keep_snapshots` Stände behalten (ADR 0001) |
| Strukturierte Daten | DuckDB (eine Datei, schnelle Analysen) | Tabellen aus Abschnitt 7.7 |
| Lauf-Artefakte | `runs/<run_id>/` | alle Agenten-Ein- und Ausgaben als JSON, Berichte, Diagramme |
| Code und Konfiguration | Git | jede Konfigurationsänderung ist ein Commit |

DuckDB reicht für das Datenvolumen eines Privatanlegers völlig. Ein Wechsel auf PostgreSQL ist nur nötig, wenn mehrere Prozesse gleichzeitig schreiben.

### 7.7 Datenmodell (Kern)

```
issuers(issuer_id PK, lei, cik, name, country, sector_sic, sic_description, sector_nace, accounting_standard,
        fiscal_year_end, state_of_incorporation, business_address, business_region, entity_type,
        filer_category, source, source_sha256, retrieved_at)
        # issuer_id: sec:<CIK> für SEC-Melder, lei:<LEI> für Emittenten ohne CIK (ab Schritt 7)
isin_cik(isin PK, cik, ticker, method[openfigi|name|manuell|keine], status[zugeordnet|unsicher|keine],
         detail, checked_at)   # ADR 0002
listings(isin PK, name, wkn, mnemonic, isin_country, currency, primary_mic, on_xetra, lei, lei_name,
         lei_status, lei_plausible, legal_country, hq_country, country, country_source[gleif|isin|konflikt],
         is_receipt, isin_valid, listed, first_seen, last_seen, snapshot_id)
universe_snapshots(snapshot_id PK, retrieved_at (UTC), source_as_of, stock_count, forced)
snapshot_raw(snapshot_id, kind[frankfurt|xetra|gleif_mapping|gleif_entities], sha256, url)
meta(key PK, value)   # schema_version
# Handelbarkeit bei Trade Republic: state/tr_checks.yaml (Lucas Prüfungen), nicht in der Datenbank
documents(doc_id PK, doc_hash, issuer_id FK, doc_type, period_end, published_at, retrieved_at, source_url,
          language, pages)   # doc_id: sec:<Accession>, doc_hash erst, wenn die Datei abgelegt ist
facts(fact_id PK, issuer_id FK, concept, internal_metric, value, unit, unit_raw, scale, currency, period_start,
      period_end, fiscal_year, fiscal_period, form, accession, published_at, source_type[xbrl|pdf_extracted|vendor],
      doc_id FK, page, xbrl_context, extraction_run_id, raw_sha256, retrieved_at, superseded_by)
      # nur über store.pit_query(as_of=...) gelesen (HR-07). superseded_by nur bei echter Änderung,
      # nicht bei bloßer Rundung (core/pit.py)
index_members(index_id, isin, tier, valid_from, valid_to, source_sha256)   # 7.9, ab Schritt 5
dq_flags(issuer_id, check_id[DQ-01..DQ-08], severity[ok|info|warnung|stopp], period_end, concept, detail,
         trace_json, checked_at)
metric_runs(run_id PK, issuer_id, as_of, stichtag, methodology_version, computed_at)   # ab Schritt 3
metrics(run_id, issuer_id, metric_id, metric_version, statistik[wert|niveau|veraenderung_vj|cagr_3j|cagr_5j|stdabw|
        steigung|plausibilitaet|aktuell|perzentil_historie], period_end, value, grund, ungereimtheit, warnungen_json, vermerke_json,
        calc_trace_json, computed_at)
        # value als Text (Decimal ungerundet), NULL = unknown mit grund. Je Firma nur der letzte Lauf.
        # calc_trace_json (mit Eingaben und Quellen) nur für Jahreswerte des letzten Geschäftsjahres
        # und die Statistik aktuell (Bewertung mit letztem Schlusskurs),
        # Vorjahre und Trends werden bei Bedarf nachgerechnet. vermerke_json: etwa abgeleitetes EBIT
price_symbols(isin PK, symbol, exch_code, method[openfigi|manuell], status[zugeordnet|unsicher|keine], detail,
              quelle_name, waehrung, boerse, warnungen_json, checked_at, retrieved_at)   # ab Schritt 4, ADR 0005
prices(isin, date, close, adj_close, volume, currency, symbol, source, raw_sha256, retrieved_at)
       # ersetzt die frühere Zeile prices(...). close um Splits bereinigt, Währung wie geliefert (GBp)
price_events(isin, date, kind[split|dividende], value, numerator, denominator, currency, symbol, source, raw_sha256)
fx_rates(date, currency, per_eur, source, raw_sha256, retrieved_at)
       # EZB-Referenzkurse, Einheiten der Währung je 1 EUR, ab 2015, ab Schritt 4 (Schema-Version 7)
hinweise(run_id, issuer_id, regel[H-01..], an_agent, abteilung, anlass, metric_id, period_end, detail,
         status[offen|beauftragt|erledigt], erstellt_at)   # 8.5, Regeln in config/hinweise.yaml
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

### 7.9 Indexstufe (Tier)

Die Indexstufe sagt, wie etabliert eine Aktie an ihrem Heimatmarkt ist: wie bekannt, wie liquide, wie gut von Analysten und Presse abgedeckt. Sie ist ein Filter und eine Markierung, kein Qualitätsurteil. Sie geht weder in die Note noch in die Kategorie ein (HR-13, Entscheidung 19 Nr. 6). Ein Titel in keinem Index kann die Note A haben.

Eine Aktie kann nicht zugleich im DAX und im S&P 500 stehen. „In allen großen Indizes“ wird deshalb so gelesen: im großen Index ihres eigenen Marktes. Das macht die Stufe zwischen Ländern vergleichbar. Ein griechischer Tier-1-Wert ist kleiner als ein amerikanischer, aber an seinem Markt ebenso etabliert. Wer absolute Größe sucht, kombiniert die Stufe mit der Größenklasse aus 3.1.

| Stufe | Bedeutung | Regel (höchste zutreffende Stufe zählt) | Beispiele für Indizes |
|---|---|---|---|
| Tier 1 | Leitwert | Mitglied im Leitindex des Heimatlandes (Land laut 7.1) oder in einem großen länderübergreifenden Leitindex | DAX, S&P 500, Nasdaq-100, Dow Jones, FTSE 100, CAC 40, SMI, AEX, IBEX 35, FTSE MIB, ATX, OMXS30, FTSE/Athex Large Cap, Nikkei 225, Hang Seng, S&P/TSX 60, Euro Stoxx 50 |
| Tier 2 | Breiter Standardwert | Mitglied im zweiten Index des Heimatmarkts oder in einem breiten globalen Standardindex für große und mittlere Werte | MDAX, S&P MidCap 400, FTSE 250, Stoxx Europe 600, MSCI World, MSCI ACWI |
| Tier 3 | Nebenwert im Index | Mitglied in einem Nebenwerte-Index | SDAX, TecDAX (ohne DAX-Mitglieder), S&P SmallCap 600, Russell 2000, MSCI ACWI Small Cap |
| Tier 4 | Ohne Index | in keinem der gelisteten Indizes | Freiverkehr, Mikrowerte, viele Hinterlegungsscheine |

Regeln:

1. Die Liste der Indizes je Stufe und je Land steht in `config/tiers.yaml` (Index, Land, Stufe, Quelle, Stand). Länder ohne eingetragenen Leitindex haben kein Tier 1, das wird in der Übersicht angezeigt statt verschwiegen.
2. Quelle der Mitglieder: Positionsdateien von ETFs, die den Index nachbilden (7.3, „ETF-Bestände“), oder die Zusammensetzung, die Börse oder Indexanbieter frei veröffentlichen. Index-Lizenzen werden nicht gekauft. Für jeden Index wird die Quelle in Schritt 5 einzeln geprüft (Nutzungsbedingungen, Format, ISIN enthalten) und in der Quellenkarte (8.9) eingetragen.
3. Zuordnung über die ISIN. Ein Hinterlegungsschein erbt die Stufe seiner Stammaktie, sobald Mehrfachlistings zusammengeführt sind (3.1), und wird bis dahin als „Stufe der Stammaktie unbekannt“ markiert.
4. Die Stufe trägt Datum und Quelle. Indexänderungen kommen mit dem wöchentlichen Universums-Lauf, ältere Stände bleiben in der Datenbank (Tabelle `index_members` mit `valid_from`, `valid_to`), damit Backtests den damaligen Stand sehen (HR-07).
