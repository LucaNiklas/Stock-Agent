# Methodik-Changelog

Jede Methodikänderung hier eintragen und methodology_version erhöhen.

## 4.0 (09.10.2026)

- Umfang auf Anzeigen und Bewerten begrenzt, Portfolio, Bestand und Steuer in Anhang A zurückgestellt.
- Kategorie "Kaufkandidat" ersetzt durch "Attraktiv", Bewertungsbedingung nur aus deterministischen Größen (Reverse-DCF, Multiples).
- DCF-Annahmen als Stufen aus der Historie statt freier Zahlen.
- K1 und K2 hängen nicht mehr an einer Tiefenanalyse.
- Reverse-DCF auf Umsatzbasis bei negativem FCF.

## 4.1 (11.10.2026)

- Agenten laufen über das Claude-Abo, Ablauf vom Python-Zustandsautomaten vorgegeben.
- Modellzuordnung je Agent (Haiku, Sonnet, Opus, optional Gemini) in config/models.yaml.
- A9 Synthese-Agent wieder in Abschnitt 8.3 (war bei Version 4.0 versehentlich im Anhang).

## 4.2 (13.10.2026)

- Vier Abteilungen (Recherche, Berechnung, Auswertung, Prüfung) mit getrennten Rechten und Übergabe über Dateien (SPEC 8.1, ADR 0003).
- Quellenkarte `config/source_map.yaml`: je Information feste Quellenreihenfolge, Python vor Agent (SPEC 8.9).
- Feste Auftragsform und Aufwandsgrenzen für Agenten (SPEC 8.10).
- Rechenweg `core/calc.py` in Bauschritt 2 vorgezogen, Datenqualität rechnet über Prüfpunkte (SPEC 12.7).
- Goldstandard startet mit mindestens 20 Fällen (SPEC 11.6).

## 4.4 (13.10.2026, Bauschritt 3, `methodology_version` der Kennzahlen 1.0)

- Erste Fassung der 33 Kennzahlen und Scores ohne Börsenkurs in `config/metrics.yaml`. Kennzahlen mit Börsenkurs, Altman Z für Produzenten und `ev_ebit_normalized` folgen in Schritt 4, der Qualitätskomposit in Schritt 5.
- `unknown` ohne Ungereimtheit, wenn eine Größe nicht aussagekräftig ist (Verlust, negatives Eigenkapital, negativer Anfangswert einer Wachstumsrate). INC-15 nur bei Datenfehlern (SPEC 12.7).
- Finanzschulden aus Teilen: Weg A `LongTermDebt` plus kurzfristige Kredite und Commercial Paper, Weg B langfristiger plus kurzfristiger Teil plus kurzfristige Kredite. Liegen beide vor, Gegenrechnung (CP-04, 0,5 Prozent).
- ROIC: Steuersatz aus Steueraufwand durch Vorsteuerergebnis, begrenzt auf 0 bis 35 Prozent, bei Verlust 0. Investiertes Kapital gleich Eigenkapital plus Finanzschulden plus Leasing minus Kasse, Durchschnitt aus Anfang und Ende.
- Piotroski mit der Bilanzsumme zu Jahresbeginn (Piotroski 2000). Altman Z'' mit Buchwert des Eigenkapitals. Beneish mit den 8 veröffentlichten Koeffizienten.
- Trends je Kennzahl (SPEC 3.4): Veränderung zum Vorjahr bei Beträgen relativ, bei Quoten in Prozentpunkten. Theil-Sen-Steigung je Geschäftsjahr, Geschäftsjahre gezählt relativ zum Stichtag (52/53-Wochen-Jahre). Streuung und Steigung erst ab 5 Jahren. CP-05 über den robusten z-Wert gegen die Vorjahre.
- Hinweisregeln H-01 bis H-09 (`config/hinweise.yaml`), Schwelle Sloan-Accruals 10 Prozent als Richtwert bis zum Branchendezil in Schritt 5.
- EBIT abgeleitet, wenn kein operatives Ergebnis gemeldet ist: Vorsteuerergebnis plus Zinsaufwand, ersatzweise minus nicht operatives Zinsergebnis netto. Mit Vermerk am Wert und an den Trends (Lucas Entscheidung 14.10.2026). Betrifft Johnson & Johnson und Nike.
- Ausreißerprüfung DQ-06 und CP-05 gegen Niveau und Trend der Vorjahre, Ausreißer nur, wenn beide auffallen (Lucas Entscheidung 14.10.2026). Bei den 10 Abnahmefirmen sinkt die Zahl der Sprung-Hinweise von 22 auf 9.

## 4.3 (13.10.2026)

- Indexstufe Tier 1 bis 4 als Filter, bezogen auf den Heimatmarkt, ohne Einfluss auf die Note (SPEC 7.9, ADR 0004).
- Freitext-Abfrage, die in einen geprüften Filter übersetzt wird (SPEC 9.9).
- Dashboard als Bedienzentrale: Suchen, Filtern und Bewerten per Klick, Claude Code im Hintergrund über `claude -p` (SPEC 13.5), Fahrplan in docs/BAUPLAN.md.
- Korrektur: Subagents können verschachtelt werden. Die Leitung bleibt beim Zustandsautomaten, kein Agent bekommt das Werkzeug `Agent` (SPEC 8.1, 16.4, ADR 0003).

## Datenqualität 1.0, Konzeptzuordnung 1.0, Quellenkarte 1.0 (13.10.2026, Bauschritt 2)

Erste Fassungen von `config/quality.yaml`, `config/concept_map.yaml` und `config/source_map.yaml`.

- Datenqualität (SPEC 3.2) als DQ-01 bis DQ-08, gerechnet über den Rechenweg mit Prüfpunkten.
  Bilanzgleichung und Summenstruktur 0,5 Prozent, zweiter Weg 1 Prozent Warnung und 5 Prozent
  Stopp, Ausreißer ab robustem z-Wert 4, Split-Verdacht bei höchstens 2 Prozent Abstand zur
  ganzen Zahl.
- Zweiter Weg: Company Facts gegen die XBRL-Instanz des letzten Jahresberichts, je Kernwert
  aus derselben Einreichung. Ein kommerzieller Anbieter fehlt weiter (SPEC 19 Nr. 1).
- Summenstruktur: Verletzung bei einem Kernwert ist Stopp, sonst Warnung. Toleranz zusätzlich
  die Summe der Rundungseinheiten (XBRL `decimals`) der beteiligten Werte.
- Konzeptzuordnung je Periode: das erste Konzept der Vorrangliste mit Wert in genau dieser
  Periode (Firmen wechseln Konzepte über die Jahre).
- Zeitpunktbezug: bloße Rundung ist kein Restatement (gröberer Wert mit mindestens drei
  gültigen Ziffern, Abstand höchstens eine halbe Rundungseinheit). Bei gleichem Wert bleibt die
  erste Veröffentlichung maßgeblich.
- Nur Werte aus Abschlussberichten (10-K, 10-Q, 20-F, 40-F, 6-K und Korrekturen). Proxy-
  Erklärungen (Tabelle Pay versus Performance) und 8-K bleiben außen vor.

## Änderungshistorie der Spezifikation

Aus `docs/spec/01-korrekturen-vorgaengerversionen.md` hierher verschoben, damit Abschnitt 1 nur die fachlichen Korrekturen enthält.

### Änderungen in Version 3

| Thema | Version 2 | Version 3 |
|---|---|---|
| Abdeckung | harte Ausschlüsse nach Größe, Tagesumsatz und Branche | alle Unternehmen werden bewertet, Größe und Liquidität wirken auf Konfidenz, Risiko und Positionsgröße (3.1) |
| Finanzwerte | ausgeschlossen | eigene Scorecards für Banken, Versicherer, Immobilien, Holdings und Wachstumsfirmen ohne Gewinn (3.11) |
| Skala | ein Score 0 bis 100 | Note A bis E, Konfidenz K1 bis K4 und Risikoklasse R1 bis R5 als getrennte Achsen (6) |
| Rechnungslegung | nicht behandelt | 14 Normalisierungsregeln IFRS gegen US-GAAP inklusive IFRS 18 ab 2027 (4) |
| Währungen | nur Umrechnung in EUR | Regeln für Bestands- und Stromgrößen, DCF-Währung, Unterwährungen, ökonomisches Exposure (5) |
| Bestand | Halten oder Verkaufsprüfung nach Score | Thesenkarten, zehn Prüfregeln, Steuerrechnung, verhaltenswissenschaftlich begründete Verkaufsgründe (10) |
| Start | ein CLI-Befehl | sechs Startwege, Kategorie-Abfrage in zwei Runden, Laufplan mit Kosten (9.7 bis 9.9) |
| Format | Bericht mit fester Gliederung | Formelregister, 14 Pflichtabschnitte je Analyse, Ungereimtheiten-Katalog, Reproduzierbarkeit (12) |
| Regeln | sieben Grundregeln | 16 harte Regeln mit technischer Durchsetzung und Test (0.1) |
| GitHub und Prompts | nicht beschrieben | Repository, Workflows, Issues für Eskalationen (16.11 bis 16.14), Prompt-Bibliothek (17) |
| Modellnamen | im Dokument | nur Modellklassen, Zuordnung in `config/models.yaml` |

### Änderungen in Version 4

| Thema | Version 3 | Version 4 |
|---|---|---|
| Umfang | Recherche plus Portfolio, Bestandsprüfung, Steuer, Gewichtungsvorschläge | nur Anzeigen und Bewerten, finanzieller Überblick je Unternehmen. Portfolio, Bestand und Steuer in Anhang A zurückgestellt |
| Universum | Börsenlisten plus Indexbestände, Handelbarkeit von Luca bestätigt | bei Trade Republic handelbare Aktien aus der öffentlichen Produktübersicht app.traderepublic.com/browse/stock (7.1) |
| Vorgehen | 14 Phasen | Bauschritte mit frühem nutzbarem Ergebnis (16.10) |
| HR-01 | Ziffern-Verbot für alle Agentenausgaben | nur für Freitextfelder, Zitate über Zitat-Gate, DCF-Annahmen als Stufen |
| HR-06 | Formeln nur in `registry.py` | Arithmetik nur in `core/`, Kennzahlen nur über die Registry |
| HR-13 | Sicherheitsmarge hing an LLM-Annahmen | Kategorie nur aus deterministischen Werten |
| Neue Regeln | | HR-17 Prompt-Injection, HR-18 Kostenlimit |
| Broker-Hook | Muster `order` | präzise Muster mit Test, `ORDER BY` erlaubt |
| Datenanbieter | Pflicht für Abgleich | optional, Default nur kostenlose Quellen |
| Branchencodes | Quelle offen | Reihenfolge in 7.8 |
| Fachlich | | negativer FCF im Reverse-DCF, Einordnung Mohanram, Teilfreistellung und Vorabpauschale in Anhang A |

### Änderungen in Version 4.1

| Thema | Version 4.0 | Version 4.1 |
|---|---|---|
| Ausführung | Python-Orchestrator mit Agent SDK und API-Schlüssel | Subagents in Claude Code über Lucas Abo, Ablauf vom Python-Zustandsautomaten vorgegeben (15.1) |
| Modelle | Klassen ohne Zuordnung | Haiku für Suche und Sammeln, Sonnet für Texte und Prüfungen, Opus nur für Fundamentalanalyse, Bewertung, Gegenposition und Forensik (8.7) |
| Zweite Modellfamilie | API eines anderen Anbieters | Gemini optional über Lucas Google-Konto, Test in Schritt 10 (8.8) |
| HR-18 | Kostenlimit in EUR | Verbrauchsgrenzen je Lauf, Kosten in EUR nur im optionalen API-Betrieb |

### Änderungen in Bauschritt 1

| Thema | vorher | jetzt |
|---|---|---|
| Quelle des Universums | Produktübersicht app.traderepublic.com/browse/stock | Instrumentenlisten der Deutschen Börse (Frankfurt, Xetra), weil die Trade-Republic-Seite hinter AWS-WAF-Bot-Schutz liegt (ADR 0001) |
| Handelbarkeit bei Trade Republic | automatisch aus der Seite | von Luca in der App geprüft, `stockagent tr-check` |

### Neue Regel HR-19 (11.10.2026)

| Thema | vorher | jetzt |
|---|---|---|
| Berechnungen | Formeln im Register, Ergebnis geprüft | jede Berechnung schrittweise über einen Rechenweg mit Prüfpunkten nach jedem Abschnitt, Abbruch bei verletztem Prüfpunkt (HR-19, 12.7). Gebaut in Bauschritt 3, genutzt ab Schritt 3 bis 5 und 7 |

### Änderungen in Version 4.2

| Thema | Version 4.1 | Version 4.2 |
|---|---|---|
| Aufbau | Liste von Agenten | vier Abteilungen mit Übergabe-Artefakten (8.1) |
| Recherche | A1 sucht frei per Websuche | Quellenkarte legt Quellen und Reihenfolge fest, Python holt alles mit fester Adresse (8.9) |
| Aufträge | frei formuliert | Ziel, Format, Quellen, Grenzen, Aufwandsgrenze (8.10) |
| Rechenweg | ab Bauschritt 3 | ab Bauschritt 2 (12.7) |
| Goldstandard | Start mit 5 Unternehmen | mindestens 20 Fälle aus 5 Unternehmen (11.6) |

### Änderungen in Version 4.3

| Thema | Version 4.2 | Version 4.3 |
|---|---|---|
| Filter | Note, Konfidenz, Risiko, Branche, Land, Größe | dazu Indexstufe Tier 1 bis 4, Kategorie, Datenlage (7.9, 13.5) |
| Start | Dialog in zwei Runden (9.7) | dazu Anfrage in eigenen Worten (9.9) |
| Oberfläche | statische Seite | Dashboard als Bedienzentrale mit Bewerten per Klick (13.5) |

