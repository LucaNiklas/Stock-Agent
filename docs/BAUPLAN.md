# Bauplan

Stand: 13.10.2026. Dieses Dokument beschreibt alle Bauschritte und sagt für jede Datei, die heute nur ein Platzhalter ist, **wann** sie gebaut wird und **was genau** hineinkommt. Verbindlich bleibt die Spezifikation (`docs/spec/`). Der Bauplan ist die Arbeitsliste dazu. Nach jedem Bauschritt werden die erledigten Zeilen hier entfernt und `docs/STATUS.md` aktualisiert.

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

### Schritt 2: Abschlussdaten USA (erledigt, LucaNiklas/Stock-Agent#7)

Python-Teil der Abteilung Recherche für die USA: Quellenkarte, Zuordnung ISIN zu CIK über OpenFIGI und die Tickerliste der SEC (ADR 0002), Stammdaten (SIC, Adresse) für alle zugeordneten SEC-Melder, Company Facts und XBRL des Originalberichts für eine Auswahl, `pit_query`, Rechenweg `core/calc.py` (vorgezogen), Datenqualität DQ-01 bis DQ-08, CLI als Paket, Befehle `sec update | show | map`.

### Schritt 3: Formelregister und Kennzahlen (erledigt, Pull Request siehe docs/STATUS.md)

Abteilung Berechnung für die USA: 33 Kennzahlen und Scores aus Abschlusswerten (SPEC 3.3, 3.5) in `config/metrics.yaml`, `core/kennzahlen.py`, `core/scores.py`, Jahresreihen aus `pit_query` (`data/inputs.py`), Trends und vertikale Analyse (`core/trends.py`, SPEC 3.4), Speicherung mit Rechenweg (Tabellen `metrics`, `metric_runs`), Hinweise an die Agenten (`config/hinweise.yaml`, Tabelle `hinweise`, SPEC 8.5), Befehl `metrics update | show`, Architekturtest HR-06. Handrechnungen aus drei Apple-10-K, Abnahme auf den 10 Firmen aus Schritt 2.

Bewusst verschoben (Lucas Entscheidung 13.10.2026): Kennzahlen mit Börsenkurs nach Schritt 4, Qualitätskomposit mit Branchenperzentilen nach Schritt 5, um Sondereffekte bereinigte Zweitreihe nach Schritt 6.

### Schritt 4: Marktdaten und Bewertung

- **Ziel:** Kurse, Zinsen, Wechselkurse, Reverse-DCF, DCF-Szenarien, Multiples.
- **Kursquelle (Lucas Entscheidung 14.10.2026, ADR 0005):** Yahoo Finance für alle Länder, nur für angefragte Titel und ihre Vergleichsgruppe. Schon gebaut im ersten Teil des Schritts (`data/sources/yahoo.py`, `prices_update.py`, Tabellen `price_symbols`, `prices`, `price_events`, Befehl `prices update | show | map`). Live getestet am 14.10.2026 mit 12 Titeln aus 9 Ländern (ADR 0005), Testdaten sind gekürzte echte Antworten.
- **Wechselkurse und Bewertungskennzahlen (zweiter Teil, 14.10.2026):** EZB-Referenzkurse ab 2015 (`data/sources/fx.py`, `fx_update.py`, Tabelle `fx_rates`, Befehl `fx update | show`), Umrechnung im Rechenweg (`core/fx.py`), zehn Kennzahlen mit Börsenkurs in `core/marktkennzahlen.py` mit Handrechnung aus Apples 10-K und Yahoo-Kursen, Statistik `aktuell` (letzter Schlusskurs) und `perzentil_historie` (Rang gegen die eigenen 10 Jahre), Tabelle „Bewertung mit Börsenkurs“ in `metrics show`. Live gerechnet für die 10 Abnahmefirmen.
- **Noch offen (dritter Teil):** Zinsen (Bundesbank, US-Treasury), Damodaran, Kapitalkosten, Reverse-DCF, DCF-Szenarien, `ev_ebit_normalized`, Altman Z für Produzenten, TTM-Werte aus Quartalen.
- **Neue Datei:** `data/sources/damodaran.py` für Risikoprämie und Branchenbetas als datierter Stand.
- **Aus Schritt 3 hierher (Lucas Entscheidung 13.10.2026):** alle Kennzahlen mit Börsenkurs aus SPEC 3.3, je über den Rechenweg mit Handrechnung wie in Schritt 3 (`tests/metrics/`): Marktkapitalisierung, Unternehmenswert (`enterprise_value` mit Brücke CP-03), KGV (`pe`), `ev_ebit`, `ev_sales`, FCF-Rendite (`fcf_yield`), Kurs-Buchwert (`pb`), Dividenden-, Rückkauf- und Aktionärsrendite (`dividend_yield`, `buyback_yield`, `shareholder_yield`). Dazu Altman Z für Produzenten (X4 mit Börsenwert) und die Zuordnung Produzent oder Nicht-Produzent über SIC, `ev_ebit_normalized` mit dem durchschnittlichen EBIT der letzten 7 bis 10 Jahre (SPEC 3.4 Nr. 4), TTM-Werte aus den letzten 8 Quartalen (SPEC 3.4 Nr. 1) und die Einordnung jeder Bewertungskennzahl gegen die eigene Historie (Perzentil über 10 Jahre, SPEC 3.3).
- **Grundlage aus Schritt 3:** Nettoverschuldung (`net_debt`, `net_debt_incl_pensions`) für die Brücke, Jahresreihen und Trends für die Annahmestufen des DCF, Speicherung in `metrics` mit Rechenweg.
- **Braucht von Luca:** für den dritten Teil Freigabe der Domains `api.statistiken.bundesbank.de` (Zinsstruktur Bundesanleihen), `home.treasury.gov` (Zinsen US-Staatsanleihen) und `pages.stern.nyu.edu` (Damodaran). Yahoo und EZB sind seit 14.10.2026 frei.
- **Abnahme:** Kurse für 10 Titel aus USA, Deutschland, UK, Japan und Hongkong mit richtigem Symbol, richtiger Währung und plausiblem letzten Kurs (Stichprobe von Hand gegen die Börsenseite). Lehrbuchbeispiel exakt reproduziert, höherer WACC ergibt niedrigeren Wert, negativer FCF korrekt behandelt, Rückrechnung CP-06 und Brücke CP-03 in jedem Lauf bestanden.

### Schritt 5: Note und erste Übersicht

- **Ziel:** Erstes nutzbares Ergebnis. Luca filtert die Liste nach Branche, Land, Stufe und Größe, wählt Titel aus, und das System bewertet sie mit Note, Konfidenz und Risiko.
- **Bewertung auf Anfrage (Lucas Entscheidung 14.10.2026, ADR 0005):** kein Gesamtlauf über alle Titel. Bewertet werden die angefragten Titel und ihre Vergleichsgruppe: dieselbe Scorecard, Branche und Region, mindestens 15 und höchstens 50 Titel. Gibt es mehr, die 50 mit dem ähnlichsten Umsatz (bekannt ohne Kurs). Kennzahlen und Kurse der Vergleichsgruppe werden gespeichert und nach einer Woche erneuert. Die Größenklasse für den Filter kommt bei unbewerteten Titeln aus dem Umsatz, bei bewerteten aus dem Börsenwert. Die Filter Note, Konfidenz und Risiko zeigen die bewerteten Titel, mit Hinweis „bisher bewertet: N Titel“. Ein Knopf „Alle bewerten“ ist vorgesehen, aber nicht Teil von Schritt 5.
- **Aus Schritt 3 hierher:** Qualitätskomposit nach Asness, Frazzini und Pedersen aus Branchenperzentilen (Bestandteile rechnet Schritt 3: Profitabilität, Wachstum, Sicherheit), Sloan-Accruals als Branchendezil, Margenstabilität (Streuung der EBIT-Marge, `stdabw` aus Schritt 3) im Qualitätsscore, Schwellen der Hinweisregeln je Branche prüfen.
- **Entsteht:** Branchencodes und Kernprodukt, Scorecard Standard, Note, Konfidenz, Risiko, Kategorie, Tabelle `grade_snapshots` für die Notenkontrolle (SPEC 14.2), Befehle `screen`, `status`, `dashboard`.
- **Neu (Oberfläche, SPEC 7.9 und 13.5):** Indexstufe Tier 1 bis 4 mit `config/tiers.yaml`, Quellenmodul `data/sources/indices.py` (ETF-Positionsdateien und freie Indexzusammensetzungen, je Index Quelle prüfen) und Tabelle `index_members`. Das Dashboard als Bedienzentrale: lokaler Server `stockagent app` mit Doppelklick-Start `Stockagent.command`, Startseite „Suchen und Bewerten“ mit Eingabefeld (Name, ISIN, WKN, Ticker und feste Wortliste für Land, Branche, Stufe, Note), Filterleiste (Stufe, Land und Region, Branche bis Unterbranche, Größe, Note, Konfidenz, Risiko, Kategorie, Handelbarkeit, Datenlage) mit Trefferzahlen, Filter in der Adresszeile, Abdeckungsanzeige, Unternehmensseite mit Notenzerlegung und Rechenweg, Stern, Notizen und Trade-Republic-Prüfung per Klick, Knopf „Daten aktualisieren“, CSV-Export. Ersetzt `universe serve` und baut auf `report/templates/universe.html` auf.
- **Braucht von Luca:** Freigabe der Domains für die Indexquellen (Liste entsteht bei der Quellenprüfung).
- **Abnahme:** Jeder angefragte US-Titel bekommt eine Note oder Status N mit Grund, mit Vergleichsgruppe von 15 bis 50 Titeln (Test mit einer Branche über 50 Titel). Eine zweite Anfrage aus derselben Branche innerhalb einer Woche ruft keine Kurse der Vergleichsgruppe neu ab (Test). Die Notenberechnung läuft über den Rechenweg mit CP-07. Jeder Titel hat eine Stufe mit Quelle und Datum. Die Filter „Tier 1, US, Branche Halbleiter“ und „Tier 4, Note A“ (unter den bewerteten Titeln) liefern dieselben Treffer wie die entsprechende SQL-Abfrage (Test). Stern, Notiz und Trade-Republic-Prüfung überleben einen Neustart des Servers. Der Server lehnt Verbindungen von anderen Rechnern ab (Test).

### Schritt 6: Tiefenanalyse Ende zu Ende

- **Ziel:** Finanzieller Überblick mit 14 Abschnitten für ein US-Unternehmen über Lucas Claude-Abo.
- **Aus Schritt 3 hierher:** Der Zustandsautomat macht aus offenen Einträgen der Tabelle `hinweise` Aufträge an den genannten Agenten (F1, A3, A4, A1) und setzt den Status auf beauftragt und erledigt. Um Sondereffekte (Wertminderungen, Veräußerungsgewinne, Restrukturierung) bereinigte Zweitreihe: A4 und A2 übernehmen die Beträge mit Beleg aus dem Bericht, Python rechnet die Zweitreihe über den Rechenweg (SPEC 3.4 Nr. 5).
- **Entsteht:** Zustandsautomat mit den vier Abteilungen (SPEC 8.1), Dossier je Unternehmen, Aufträge nach SPEC 8.10 aus der Quellenkarte, Nachforderung, Werkzeugrechte je Abteilung, Annahme von Agentenausgaben, Werkzeuge, Prompts, Agentenvorlagen in `agents_src/` (A1, A3, A4, A5, A7, A9, J1, J2) mit Modellen aus `config/models.yaml`, Berichtsvorlagen, Skill `/analyze-stock`, Befehl `analyze`. Der `SubagentStop`-Hook ruft `stockagent accept`.
- **Neu (Oberfläche, SPEC 13.5):** Knopf „Tiefenanalyse starten“ auf der Unternehmensseite und „Auswahl bewerten“ in der Liste starten Claude Code im Hintergrund (`claude -p "/analyze-stock <ISIN>"` mit `stream-json`, feste Rechte, `--permission-prompts none`). Fortschrittsanzeige je Abteilung, Warteschlange `state/analysis_queue.yaml`, wenn schon eine Analyse läuft, Anzeige des Abo-Verbrauchs aus `log.jsonl`. Vorher prüfen: läuft `claude -p` über die Anmeldung des Abos auf Lucas Mac.
- **Abnahme:** Alle Ausgaben schemakonform, jeder Agent lief mit seinem Modell, ein Schritt außerhalb der Reihenfolge wird abgelehnt, alle 14 Abschnitte vorhanden. Ein Klick auf „Tiefenanalyse starten“ führt ohne Terminal bis zum fertigen Überblick auf der Unternehmensseite. Ein geschlossener Browser bricht die Analyse nicht ab.

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

- **Ziel:** Alles über das Dashboard: Suche in eigenen Worten, Bewerten ganzer Trefferlisten, alle Ansichten. Claude Code nur im Hintergrund.
- **Entsteht:** Befehl `stockagent run` mit Dialog (`questionary`), Laufplan, alle Ansichten aus SPEC 13.3 (Änderungen, Karte Branche mal Land, Vergleich, Eskalationen, Historie, Methodik).
- **Neu (Oberfläche, SPEC 9.9 und 13.5):** Eingabefeld des Dashboards versteht ganze Sätze („Tier 1 Griechenland Automobil, bewerte sie“): Wortliste zuerst, sonst Übersetzung über `claude -p` mit `--json-schema` ohne Werkzeuge. Verstandener Filter als änderbare Schaltflächen mit Trefferzahl, Vorschlag bei null Treffern, „Alle bewerten“ mit Laufplan und Bestätigung, gespeicherte Ansichten in `state/views.yaml`. Der Dialog `stockagent run` und `/stockagent` bleiben als zweiter Weg.
- **Abnahme:** Alle Startwege aus SPEC 9.6 funktionieren, Antworten in `request.json`. Zehn Beispielsätze aus einer Testliste werden in den richtigen Filter übersetzt, ein Satz mit unbekanntem Land oder unbekannter Branche wird abgelehnt statt geraten.

### Schritt 12: Zeitplan (optional)

- **Ziel:** Läufe ohne Luca, etwa wöchentlich.
- **Neue Dateien:** `.github/workflows/scheduled-run.yml` oder ein lokaler Zeitplan in der Claude-Desktop-App, Profil `scheduled` in `config/run_profiles.yaml`, Benachrichtigung.
- **Braucht von Luca:** Entscheidung, ob ein API-Schlüssel mit Kosten pro Token genutzt werden soll (SPEC 19 Nr. 4).
- **Abnahme:** Drei Läufe hintereinander ohne manuellen Eingriff.

### Nach Schritt 12: Teilen und Unabhängigkeit von Claude (Lucas Ziel, 14.10.2026)

Erst nur für Luca, später für alle, die es nutzen wollen. Zwei Stufen nach dem bisherigen Plan, Einzelheiten in SPEC 18.6:

- **Baustein F, Teilen:** Andere installieren die Plattform bei sich und nutzen sie mit ihrem eigenen Claude-Abo. Dazu gehören eine Installationsanleitung, Einrichtung per Befehl (`stockagent init`: Ordner, eigener SEC-User-Agent, Konfiguration), Trennung von Lucas persönlichen Daten (`state/`) und dem geteilten Code, Lizenz, Tests auf macOS, Windows und Linux.
- **Baustein G, autonom:** Dieselben Funktionen ohne Claude. Die Agenten laufen über eine austauschbare Schnittstelle, hinter der wahlweise Claude, ein anderes Sprachmodell oder ein lokales Modell steht. Die Prüfagenten und der Goldstandard (Schritt 10) zeigen, ob ein Ersatz gut genug ist.

Was schon jetzt dafür gilt: Rechnen, Prüfen und Speichern laufen vollständig in Python ohne Sprachmodell, alle Datenquellen sind frei zugänglich, keine festen Pfade oder persönlichen Angaben im Code, Geheimnisse nur über Umgebungsvariablen.

## Fahrplan Oberfläche

Ziel ist ein Dashboard als Bedienzentrale: Luca tippt nichts in Claude Code oder ins Terminal (SPEC 13.5). Claude Code läuft im Hintergrund, gestartet vom Dashboard über Lucas Abo. Jeder Schritt erweitert dieselbe Seite.

| Nach Schritt | Sehen | Tun im Dashboard |
|---|---|---|
| 1 und 2 (heute) | Universum als HTML mit Suche, `sec show` im Terminal | noch nichts, Prüfungen über das Terminal |
| 5 | Startseite „Suchen und Bewerten“, Übersicht aller Titel mit Note, Konfidenz, Risiko, Kategorie, Tier, Branche, Land, Filterleiste, Abdeckungsanzeige, Unternehmensseite mit Notenzerlegung und Rechenweg | Start per Doppelklick, suchen (Name, ISIN, feste Wortliste), filtern, sortieren, exportieren, Stern, Notiz, Trade-Republic-Prüfung, Daten aktualisieren |
| 6 | Fortschritt je Abteilung und finanzieller Überblick auf der Unternehmensseite, Abo-Verbrauch | Tiefenanalyse per Klick starten, einzeln oder als Auswahl, Warteschlange |
| 7 und 8 | dieselben Ansichten auch für EU-Werte und mit den Branchen-Scorecards | mehr Titel mit Note |
| 9 | Insider-Zeitachse auf der Unternehmensseite, Insider als Filter | |
| 10 | Eskalationen mit beiden Werten und Quellen | Entscheidungen direkt auf der Seite |
| 11 | Änderungen seit dem letzten Lauf, Karte Branche mal Land, Vergleich, Historie, Methodik | Suche in ganzen Sätzen, „Alle bewerten“ mit Laufplan, gespeicherte Ansichten |

## Platzhalter: wann und was

Jede dieser Dateien existiert schon und nennt im Kopf denselben Bauschritt und Inhalt. Ordner mit `/` am Ende enthalten eine `README.md`, weil Git leere Ordner nicht speichert.

| Schritt | Datei | Zweck | Was genau hineinkommt |
|---|---|---|---|
| 4 | `src/stockagent/core/fx.py` | Währungsregeln (SPEC 5.2) | Reine Funktionen: Bilanzposten zum Stichtagskurs, GuV und Cashflow zum Periodendurchschnitt, Unterwährungen (GBX, ZAc, ILA), ADR-Verhältnis, Fisher-Umrechnung von Diskontsätzen, Plausibilitätsprüfung INC-13. Über den Rechenweg mit CP-01 und CP-02 |
| 4 | `src/stockagent/core/valuation.py` | Bewertung (SPEC 3.6) | Reverse-DCF (auf FCF- und Umsatzbasis), DCF in drei Szenarien mit Annahmestufen aus der Historie, Multiples gegen Historie und Vergleichsgruppe, Sensitivitätsmatrix, Unternehmenswert-Brücke, deterministische Bewertungsbedingung. Prüfpunkte CP-03 (Brücke) und CP-06 (Rückrechnung) in jedem Lauf |
| 4 | `src/stockagent/data/sources/fx.py` | Wechselkurse (SPEC 5.2) | EZB-Referenzkurse über die SDMX-API, täglich, mit Datum und Quelle. Daraus Stichtags- und Durchschnittskurse |
| 4 | `src/stockagent/data/sources/rates.py` | Risikofreie Zinsen (SPEC 3.6, 7.3) | 10-jährige Bundesanleihe (Bundesbank-Zinsstrukturkurve) und 10-jährige US-Treasury (FRED), jeweils mit Datum. Grundlage für WACC und Endwachstum |
| 5 | `config/scorecards.yaml` | Scorecard-Zuordnung (SPEC 3.11) | In Schritt 5 nur `standard` mit ihren Kennzahlen je Säule. Regeln für die Zuordnung über SIC, NACE und Kennzahlen. Weitere Scorecards in Schritt 8 |
| 5 | `config/scoring.yaml` | Gewichte und Schwellen der Bewertungsskala (SPEC 6) | Vergleichsgruppe mindestens 15, höchstens 50 Titel, Auswahl nach ähnlichstem Umsatz, Kurse der Gruppe gelten 7 Tage (ADR 0005). Säulengewichte (Qualität 25, Bewertung 25, Stabilität 15, Wachstum 15, Kapitalallokation 10, Insider 10 Prozent), Kappungsgrenzen, Notenschwellen A bis E, Bedingungen für K1 bis K4 und R1 bis R5, Kategorien, Hysterese, Mindestgröße der Vergleichsgruppe (15), `min_discount_to_multiples`, Überprüfungskriterium der Notenkontrolle |
| 5 | `config/sectors.yaml` | Branchenliste und Abbildung (SPEC 7.8, 9.7) | 11 Hauptbranchen mit Unterbranchen und deutscher Bezeichnung, Abbildung SIC- und NACE-Bereiche auf diese Branchen, Abbildung Wikidata-Branchen auf NACE |
| 5 | `src/stockagent/core/decisions.py` | Kategorie und Zustandsautomat (SPEC 6.5, HR-13) | Deterministische Kategorie (Attraktiv, Beobachten, Neutral, Unattraktiv, Eskaliert, Nicht bewertbar), Hysterese über zwei Läufe (9.5). Sprachmodelle haben nur die Übergänge `downgrade` und `escalate` |
| 5 | `src/stockagent/core/grading.py` | Note, Konfidenz, Risikoklasse (SPEC 6) | Perzentile je Kennzahl in der Vergleichsgruppe mit stufenweiser Erweiterung, Säulenwerte, Gesamtwert, Kappungen, Note A bis E oder N, Konfidenz K1 bis K4, Risikoklasse R1 bis R5. Über den Rechenweg mit CP-07 |
| 5 | `src/stockagent/dashboard/__init__.py` | Paket Dashboard | Paketkennung, keine Logik |
| 5 | `src/stockagent/dashboard/build.py` | Dashboard bauen (SPEC 13.3) | Schreibt eine einzelne HTML-Datei mit eingebetteten Daten. Ansicht Übersicht (alle Unternehmen mit Note, Konfidenz, Risiko, Branche, Land, filterbar) und Unternehmensseite mit Notenzerlegung. Weitere Ansichten in Schritt 11 |
| 5 | `src/stockagent/dashboard/template.html` | HTML-Vorlage des Dashboards | Seitengerüst mit Filtern, Tabelle, Hell- und Dunkelmodus, Notenzerlegung. Baut auf `report/templates/universe.html` auf |
| 5 | `src/stockagent/data/sources/sectors.py` | Branchencodes (SPEC 7.8) | SIC liegt seit Schritt 2 in `issuers`. Geschäftsbeschreibung für US-Firmen aus Item 1 des 10-K (die Submissions der SEC enthalten keine). Reihenfolge: SIC aus den SEC-Submissions, ggf. Datenanbieter, Wikidata (Eigenschaft Branche, über ISIN oder LEI), sonst Vorschlag von A0 mit Lucas Bestätigung. Quelle und Datum je Code, unsichere Zuordnung senkt die Konfidenz. Auch Kurzbeschreibung des Kernprodukts, soweit die Quelle sie liefert |
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
| 11 | `.claude/skills/stockagent/SKILL.md` | Skill /stockagent | Freitext-Abfrage nach SPEC 9.9 oder Kategorie-Abfrage in zwei Runden mit AskUserQuestion (SPEC 9.7), Abarbeiten der Warteschlange aus `state/analysis_queue.yaml`, Laufplan zeigen, nach Bestätigung `stockagent run` starten, Fortschritt melden, Ergebnis zusammenfassen, Dashboard öffnen |
| 11 | `config/run_profiles.yaml` | Laufprofile (SPEC 9.6, 9.7) | Profile für `stockagent run --profile`: Kategorie, Größenklassen, Tiefe, Höchstzahl Tiefenanalysen. In Schritt 12 das Profil `scheduled` |

## Neue Dateien ohne heutigen Platzhalter

| Schritt | Datei | Inhalt |
|---|---|---|
| 5 | `config/tiers.yaml` | Indizes je Stufe und Land mit Quelle und Stand (SPEC 7.9) |
| 5 | `src/stockagent/data/sources/indices.py` | Indexmitglieder aus ETF-Positionsdateien und freien Zusammensetzungen |
| 5 | `src/stockagent/dashboard/server.py` | Lokaler Server `stockagent app` auf 127.0.0.1: Dashboard plus Schnittstelle, schreibt nur nach `state/` und `runs/`, startet ab Schritt 6 Claude Code im Hintergrund |
| 5 | `Stockagent.command` | Doppelklick-Start unter macOS: `uv run stockagent app` im Projektordner |
| 5 | `state/notes.yaml` | Lucas Notizen je Titel |
| 6 | `state/analysis_queue.yaml` | Warteschlange angeforderter Tiefenanalysen |
| 11 | `state/views.yaml` | Gespeicherte Ansichten und Abfragen |
| 4 | `src/stockagent/data/sources/damodaran.py` | Risikoprämie, Branchenbetas und -multiples als datierter Stand |
| 6 | `agents_src/<agent>.md` | Vorlagen A1, A3, A4, A5, A7, A9, J1, J2 mit Pflicht-Präambel |
| 7 | `src/stockagent/data/sources/pdf.py` | PDF-Rückfall mit Docling (SPEC 7.4) |
| 10 | `src/stockagent/agents/tools/gemini.py` | Gemini CLI als externer Prüfer (SPEC 8.8) |
| 10 | `.github/workflows/eval.yml` | Goldstandard-Lauf bei Änderungen an Prompts, Agenten oder Konfiguration |
| 12 | `.github/workflows/scheduled-run.yml` | Zeitplan, nur bei API-Betrieb |

## Bewusst behalten, obwohl fast leer

- `docs/spec/10-bestandspruefung-und-verkaufslogik.md` und Abschnitt 3.10: nur ein Verweis auf Anhang A. Sie bleiben, damit die Abschnittsnummern stimmen, auf die andere Stellen der Spezifikation verweisen.
