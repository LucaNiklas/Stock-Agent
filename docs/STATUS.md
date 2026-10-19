# Projektstand (Übergabe)

Stand: 14.10.2026, Bauschritt 4 begonnen. Diese Datei zuerst lesen, wenn eine neue Sitzung beginnt. Sie wird am Ende jedes Bauschritts aktualisiert.

## Was das System ist

Recherche- und Bewertungssystem für Aktien, die bei Trade Republic handelbar sind. Es zeigt nur an und bewertet. Es gibt keine Orders, keinen Depotzugriff und keine Budget- oder Allokationsplanung. Die Spezifikation liegt in `docs/spec/` (Inhaltsverzeichnis `docs/SPEC.md`, Version 4.5), die harten Regeln stehen in `docs/spec/00-arbeitsanweisung.md`.

## Arbeitsweise mit Luca

- Vor jedem Bauschritt erklären, was gebaut wird. Am Ende Vorgehen und Ergebnis selbst auf Fehler und Verbesserungen prüfen und das Ergebnis berichten.
- Je Bauschritt ein Branch `schritt-NN-kurzname` und ein Pull Request. Gemergt wird erst nach Lucas Freigabe, nie direkt auf `main` pushen.
- Agenten laufen später über Lucas Claude-Abo, nicht über einen API-Schlüssel. Haiku sucht und sammelt, Sonnet schreibt und prüft, Opus nur für die anspruchsvollsten Schritte (`config/models.yaml`, SPEC 8.7). Gemini ist ein optionaler Prüfer, sein Test kommt in Schritt 10.
- Kommunikation auf Deutsch.
- **Rechenregel (HR-19, Lucas Vorgabe):** Jede Berechnung läuft schrittweise. Nach jedem Abschnitt wird das bisher Gerechnete mit einem Prüfpunkt kontrolliert, erst dann geht es weiter. Ein verletzter Prüfpunkt stoppt die Rechnung. Details in SPEC 12.7, gebaut als `core/calc.py` in Bauschritt 2 (vorgezogen), genutzt ab Schritt 2 in jeder Rechnung.

## Erledigt

| Schritt | Inhalt | Pull Request |
|---|---|---|
| Spezifikation 4.0/4.1 | Umfang nur Anzeigen und Bewerten, Bauschritte statt Phasen, Ausführung über das Abo, Modell je Agent | LucaNiklas/Stock-Agent#1 |
| 0 Gerüst | uv, CI, Grundtypen (`Money`, `Fact`, `FreeText`, `Claim`), Gates, CLI-Gerüst, Hooks, Erzeugung der Agent-Dateien | LucaNiklas/Stock-Agent#2 |
| 1 Universum | Aktienliste der Deutschen Börse, LEI und Länder aus der GLEIF, Lucas Trade-Republic-Prüfungen, Anzeige im Terminal und als HTML | LucaNiklas/Stock-Agent#3 (gemergt 11.10.2026) |
| Spezifikation 4.2 | Vier Abteilungen, Quellenkarte, Auftragsform, Rechenweg nach Schritt 2 vorgezogen (ADR 0003) | LucaNiklas/Stock-Agent#6 |
| 2 Abschlussdaten USA | ISIN zu CIK über OpenFIGI (ADR 0002), SIC und Adresse der SEC, Company Facts mit Zeitpunktbezug, Rechenweg `core/calc.py`, Datenqualität DQ-01 bis DQ-08, CLI als Paket | LucaNiklas/Stock-Agent#7 |
| Spezifikation 4.3 | Dashboard als Bedienzentrale, Indexstufe Tier 1 bis 4, Suche in eigenen Worten (ADR 0004) | LucaNiklas/Stock-Agent#8 |
| 4 Kurse (Teil 1) | Kursquelle Yahoo für alle Länder auf Anfrage, Zuordnung über OpenFIGI, Befehl `prices`, Plan: Bewertung auf Anfrage, Vergleichsgruppe 15 bis 50 (ADR 0005) | LucaNiklas/Stock-Agent#11 |
| 4 Bewertung (Teil 2) | Wechselkurse der EZB, Umrechnung im Rechenweg, zehn Kennzahlen mit Börsenkurs, Bewertung mit aktuellem Kurs, Rang gegen die eigenen 10 Jahre, Dividenden-Gegenprobe | LucaNiklas/Stock-Agent#12 |
| 4 Kapitalkosten (Teil 3a) | Zinsen (Bundesbank, Treasury), Damodaran, WACC, Reverse-DCF, normalisiertes EV/EBIT, Altman Z für Produzenten (ADR 0006) | Branch `schritt-04-kapitalkosten` |
| 4 DCF und TTM (Teil 3b) | DCF-Szenarien Bear, Base, Bull mit Sensitivität, TTM-Werte aus Quartalsberichten | Branch `schritt-04-dcf` |
| 3 Kennzahlen | 33 Kennzahlen und Scores ohne Börsenkurs mit Rechenweg und Prüfpunkten, Trends, vertikale Analyse, Speicherung, Hinweise an die Agenten, Befehl `metrics`, Architekturtest HR-06 | LucaNiklas/Stock-Agent#9 |

## Stand der Daten (lokal, nicht im Repository)

- `data/stockagent.duckdb` (Schema-Version 8, Versionen 3 bis 7 werden beim Öffnen ohne Datenverlust aufgerüstet): 14.509 Aktien, Stand der Quelle 12.10.2026.
- Zuordnung zur SEC (Lauf vom 13.10.2026): von 4.021 US-ISINs sind 3.117 einer CIK zugeordnet (3.052 verschiedene Firmen), 9 unsicher, 895 ohne SEC-Melder (davon 845 Hinterlegungsscheine, meist nicht gesponserte ADRs, 69 davon nur ADR-Registrierungen der Depotbank). Stammdaten liegen für alle 3.052 vor. Die SEC selbst führt bei 115 keinen SIC-Code (überwiegend geschlossene Fonds) und bei 2 keine Geschäftsadresse. 2.697 haben eine US-Geschäftsadresse.
- Die 9 unsicheren Zuordnungen zeigt `stockagent sec show <ISIN>` mit Grund (meist Umbenennungen wie Hypera/Hypermarcas oder Verwechslungen bei OpenFIGI wie Helix Energy mit dem Ticker von Hornbeck Offshore). Festlegen mit `stockagent sec map <ISIN> <CIK>|keine`.
- Abschlusswerte und Prüfungen bisher für die 10 Abnahmefirmen: Apple, Microsoft, Coca-Cola, Johnson & Johnson, Caterpillar, Procter & Gamble, Nike, Walmart, JPMorgan, PagerDuty. Alle erfüllen die Bilanzgleichung für zehn Jahre, alle verfügbaren Kernwerte stimmen auf dem zweiten Weg mit dem Originalbericht überein.
- Kennzahlen (Lauf vom 13.10.2026) für die 10 Abnahmefirmen: zusammen 306 von 330 Jahreswerten im letzten Geschäftsjahr berechnet, kein Prüfpunkt gestoppt. Die fehlenden: JPMorgan 20 (Bank, eigene Scorecard in Schritt 8), Apple, Caterpillar und Nike je 1 (kein Zinsaufwand gemeldet, Zinsdeckung unbekannt), PagerDuty 1 (Gewinn je Aktie vor 5 Jahren negativ, Wachstumsrate in Prozent nicht berechenbar). Bei Johnson & Johnson und Nike ist das EBIT abgeleitet und markiert. Speicher je Firma rund 100 KB. Die Werte aus der Datenbank stimmen für Apple bei allen 33 Kennzahlen mit der Handrechnung aus den 10-K überein.
- Wechselkurse der EZB (Lauf vom 14.10.2026): 86.703 Referenzkurse für 29 Währungen ab 2015.
- Bewertung (Lauf vom 14.10.2026, Kurse bis 13.10.2026) für die 10 Abnahmefirmen: 43 Kennzahlen je Firma, davon 10 mit Börsenkurs. Es fehlen JPMorgan 5 (Unternehmenswert, EV/EBIT, EV/Umsatz und Aktionärsrendite brauchen die Nettoverschuldung, FCF-Rendite den Capex: Bank, Schritt 8) . PagerDuty zahlt keine Dividende: Dividendenrendite 0 % (Bericht und Yahoo zeigen keine), Aktionärsrendite 9,45 % aus Rückkäufen und Schuldenabbau. Die Werte aus der Datenbank stimmen für Apple bei allen 43 Kennzahlen mit der Handrechnung überein. Beispiel Apple: KGV 34,2 am Geschäftsjahresende, 45,7 mit dem Kurs vom 13.10.2026, so hoch wie in keinem der letzten 10 Geschäftsjahre.
- Zinsen und Damodaran (Lauf vom 19.10.2026): 10-jährige Zinsen EUR und USD ab 2015, Damodaran-Stand Januar 2026 (96 Branchen, 48.144 Firmen), Risikoprämie monatlich bis Oktober 2026 (3,70 %).
- Kapitalkosten (Lauf vom 19.10.2026, 10 Abnahmefirmen): WACC zwischen 6,4 % (Coca-Cola) und 12,0 % (PagerDuty), Apple 9,37 %. Implizites FCFF-Wachstum über 10 Jahre am Geschäftsjahresende: Procter & Gamble 4,5 %, Johnson & Johnson 6,1 %, Coca-Cola 9,8 %, Caterpillar 10,6 %, Nike 11,5 %, Apple 15,5 %, Walmart 16,2 %, Microsoft 16,8 %, PagerDuty -2,0 %. JPMorgan ohne WACC (Bank). Rückrechnung CP-06 bei allen bestanden. Die Werte aus der Datenbank stimmen für Apple bei allen 47 Kennzahlen mit der Handrechnung überein.
- DCF-Szenarien mit aktuellem Kurs (Lauf vom 19.10.2026, Wert je Aktie Bear / Base / Bull): Apple 83 / 107 / 152 USD (Kurs 341), Microsoft 198 / 324 / 416, Caterpillar 144 / 287 / 488 (Kurs 773), Johnson & Johnson 101 / 141 / 167, Procter & Gamble 102 / 117 / 133, Coca-Cola 29 / 48 / 58, Walmart 29 / 54 / 63, Nike 27 / 52 / 69. PagerDuty ohne DCF (operativer Verlust, Scorecard Schritt 8), JPMorgan ohne (Bank). Die Szenarien stützen sich nur auf die eigene Historie und liegen deshalb bei Wachstumswerten weit unter dem Kurs. Das zeigt dasselbe wie der Reverse-DCF.
- TTM bis zum letzten Quartal für Apple, Caterpillar, Coca-Cola, Johnson & Johnson, Nike, Walmart und PagerDuty. Microsoft und Procter & Gamble haben ihr Geschäftsjahr gerade abgeschlossen. Bei Caterpillar, JPMorgan und PagerDuty fehlt im Quartalsbericht der Wert `LongTermDebt`, dort sind die TTM-Werte mit Unternehmenswert `unknown`.
- `data/raw/`: Rohdateien mit SHA-256, auch jede SEC- und OpenFIGI-Antwort.
- `state/tr_checks.yaml`: Lucas Prüfungen in der Trade-Republic-App. Noch leer.
- `state/cik_overrides.yaml`: Lucas Zuordnungen zur SEC (`stockagent sec map`). Noch leer.
- Nach einem frischen Klonen: `uv run stockagent universe update` (etwa 2 Minuten), dann `uv run stockagent sec update` (etwa 20 Minuten wegen der Grenze von OpenFIGI), dann `uv run stockagent sec update --isin <ISIN>` für Abschlusswerte.

## Bauschritt 2 im Überblick

- Recherche USA nach der Quellenkarte `config/source_map.yaml`: OpenFIGI (ISIN -> Ticker), Tickerliste der SEC (Ticker -> CIK), Submissions (SIC, Adresse, Gründungsstaat, Geschäftsjahresende), Company Facts (Abschlusswerte), XBRL des letzten Jahresberichts (zweiter Weg).
- Zeitpunktbezug über `store.pit_query(as_of=...)`. Bloße Rundung in späteren Berichten gilt nicht als Restatement. Nur Werte aus Abschlussberichten, nicht aus Proxy-Erklärungen oder 8-K.
- Datenqualität DQ-01 bis DQ-08 (SPEC 3.2) über den Rechenweg mit Prüfpunkten. Jede Prüfung nennt, was sie geprüft hat. `stockagent sec show <ISIN>` zeigt alles.
- Handprüfung gegen die 10-K-Dokumente von Apple, PagerDuty und JPMorgan mit Seitenzahl in `tests/test_sec_abnahme.py`.

## Wichtige Befehle

```bash
uv run stockagent universe update [--refresh] [--force]
uv run stockagent universe show --suche siemens
uv run stockagent universe serve
uv run stockagent render-agents
uv run stockagent tr-check <ISIN> ja|nein
uv run stockagent sec update [--isin <ISIN>] [--refresh]
uv run stockagent sec show <ISIN>
uv run stockagent sec map <ISIN> <CIK>|keine
uv run stockagent prices update -i <ISIN> [--refresh]
uv run stockagent prices show <ISIN>
uv run stockagent prices map <ISIN> <SYMBOL>|keine
uv run stockagent markt update [--refresh]
uv run stockagent markt show
uv run stockagent markt branche <ISIN> "<Branche bei Damodaran>"
uv run stockagent fx update [--refresh]
uv run stockagent fx show USD [--datum JJJJ-MM-TT]
uv run stockagent metrics update [--isin <ISIN>] [--as-of JJJJ-MM-TT]
uv run stockagent metrics show <ISIN> [--rechenweg <id> [--jahr J | --trend T | --aktuell]]
uv run pytest && uv run ruff check . && uv run mypy
```

## Wichtige Entscheidungen

- ADR 0001 (`docs/adr/0001-universum-quelle.md`): Die Trade-Republic-Produktübersicht liegt hinter dem AWS-WAF-Bot-Schutz und wird nicht automatisch abgerufen. Basis sind deshalb die Listen der Deutschen Börse, und die Handelbarkeit prüft Luca selbst. finanzen.net verbietet automatisierte Abfragen und dient nur als Stichprobe von Hand.
- Länder: Hauptsitz und Rechtssitz (Rechtsordnung) laut GLEIF, nur wenn der Name passt und kein Widerspruch zur ISIN besteht. Sonst wird das ISIN-Land als unsicher markiert.
- Keine Order-Sperre nötig (Lucas Entscheidung). HR-09 ist eine Umfangsregel.
- ADR 0002: ISIN zu CIK über OpenFIGI und die Tickerliste der SEC, Unsicheres bleibt leer. onvista und finanzen.net werden nicht automatisch abgefragt.
- ADR 0003: vier Abteilungen (Recherche, Berechnung, Auswertung, Prüfung) mit Quellenkarte. Python holt alles mit fester Adresse, Agenten suchen nur, wo es keine gibt.
- Werte für Abschlusszahlen nur für eine Auswahl laden (Lucas Entscheidung 13.10.2026).
- ADR 0006 (19.10.2026): Kapitalkosten aus Treasury- und Bundesbank-Zins, Damodarans Risikoprämie und Branchenbeta (Zuordnung über Börse und Kürzel, sonst SIC), gesetzlicher Steuersatz je Land, Fremdkapitalaufschlag aus synthetischem Rating. Reverse-DCF über 10 Jahre mit Rückrechnung.
- ADR 0005 (14.10.2026): Bewertung auf Anfrage statt Gesamtlauf, Vergleichsgruppe 15 bis 50 Titel, Kursquelle Yahoo Finance für alle Länder mit eigenem kleinem Abrufmodul, ohne Schlüssel. Polygon bleibt als zweite Quelle für US-Kurse vorgesehen.

## Offen und bekannt

- **Geschäftsbeschreibung fehlt noch.** Die SEC liefert sie nicht strukturiert (Feld `description` leer). Sie kommt in Schritt 5 aus Item 1 des 10-K. SIC-Codes liegen für alle zugeordneten SEC-Melder vor. Übrige: SPEC 7.8 (Wikidata, dann Lucas Bestätigung).
- **Mehrfachlistings:** Ein Unternehmen erscheint mehrfach (Stammaktie, ADR, CDR). Die Zusammenführung über LEI und CIK ist vorbereitet (`issuers.lei`, `issuers.cik`), aber noch nicht gebaut.
- **Länder ausländischer SEC-Melder:** Die SEC nennt ihr Land nur als eigenen Code (etwa `2M` für Deutschland). Gespeichert sind Code und Name. Eine Abbildung auf ISO-Codes fehlt noch.
- **Länder ohne LEI (6.368 Aktien):** nur das ISIN-Land, unsicher. Für zugeordnete SEC-Melder liegt jetzt die Geschäftsadresse vor.
- **Unsicherheit bei Umbenennungen:** Führt die GLEIF noch den alten Namen, fällt das Land auf das ISIN-Land zurück (232 Fälle).
- **Abgeleitetes EBIT enthält übrige nicht operative Posten** (Kursgewinne, Beteiligungserträge). Bei Johnson & Johnson springt die EBIT-Marge 2025 dadurch auf 35,6 Prozent, und die Ausreißerprüfung meldet das an A4. Die um Sondereffekte bereinigte Reihe aus Schritt 6 wird das erklären.
- **DQ-06 in `dq_flags`** stammt noch aus dem Lauf von Schritt 2 mit der alten Ausreißerprüfung. Beim nächsten `sec update --isin` wird sie mit der neuen Prüfung ersetzt.
- **Banken:** Bruttomarge, Free Cashflow, Current Ratio und Finanzschulden passen nicht auf Banken (JPMorgan: 20 Kennzahlen `unknown` mit Grund). Eigene Scorecard in Schritt 8.
- **Zweite unabhängige Quelle:** Für Abschlusszahlen ist der zweite Weg das XBRL des Originalberichts. Für Kurse gibt es keine Gegenprobe, nur Plausibilitätsprüfungen (ADR 0005).
- **Firmen ohne Dividende (Lucas Entscheidung 14.10.2026):** 0 % nur, wenn weder der Bericht noch Yahoo im Geschäftsjahr eine Dividende zeigt. Zeigt Yahoo eine und der Bericht nicht, bleibt der Wert `unknown`, und Hinweis H-10 geht an die Recherche (fehlende Zuordnung des XBRL-Konzepts). Jahre vor dem ersten gespeicherten Kurs haben keine Gegenprobe.
- **Rang gegen die eigene Geschichte:** Der Rang sagt nur, wo der Wert in den eigenen 10 Jahren liegt. Ob hoch gut oder schlecht ist, hängt von der Kennzahl ab (hohes KGV teuer, hohe FCF-Rendite günstig). Das ordnet die Note in Schritt 5 ein.
- **Kurse von Yahoo:** live getestet am 14.10.2026 mit 12 Titeln aus USA, Deutschland, UK, Japan, Hongkong, Kanada, Australien, Niederlande und Schweiz (ADR 0005). Inoffizielle Quelle, kann ausfallen. Kurse liegen lokal für diese 12 Titel vor.
- **Vorzugsaktien und Anleihen im Universum:** Die Deutsche Börse führt einige Vorzugsaktien und nachrangige Anleihen als `CS` (etwa „HANCOCK WHITNEY SU.NTS 25“). Sie werden dem richtigen Emittenten zugeordnet, sind aber keine Stammaktie. Bereinigung des Universums offen.
- **Gelöschte Handzuordnung:** Entfernt Luca einen Eintrag aus `state/cik_overrides.yaml`, gilt die alte Zuordnung bis zur nächsten Neuprüfung (90 Tage). Sofort wirkt `sec map <ISIN> <CIK>`.
- Das Feld „Primary Market MIC Code“ der Deutschen Börse ist kein verlässlicher Primärmarkt und darf nicht als Kursquelle dienen.

## Bauschritt 3 im Überblick

- Abteilung Berechnung, nur Python: `data/inputs.py` baut aus `pit_query` die Jahresreihen (bis 11 Jahre), `core/kennzahlen.py` und `core/scores.py` rechnen 33 Kennzahlen je Geschäftsjahr über den Rechenweg, `core/trends.py` Vorjahresveränderung, CAGR, Streuung, Theil-Sen-Steigung und CP-05, `metrics_update.py` speichert alles mit Rechenweg.
- Drei Arten von `unknown`: Eingabe fehlt, nicht aussagekräftig (etwa Verlust im Nenner) und Prüfpunkt verletzt (INC-15). Nur die dritte ist ein Datenfehler.
- Hinweise an die Agenten (`config/hinweise.yaml`, H-01 bis H-09): die Übergabe von der Berechnung an Auswertung, Prüfung und Recherche. Ab Schritt 6 macht der Zustandsautomat daraus Aufträge.
- Handrechnung je Kennzahl in `tests/metrics/` mit Seitenangaben aus drei Apple-10-K. Architekturtest HR-06 in `tests/test_architektur.py`.

## Ziel Teilen und Autonomie (14.10.2026)

Erst für Luca, später für alle. Nach Schritt 12 kommen Baustein F (andere installieren die Plattform mit eigenem Claude-Abo) und Baustein G (alle Funktionen ohne Claude, Agenten über eine austauschbare Schnittstelle). Die Regeln, die schon jetzt gelten, stehen in SPEC 18.6.

## Oberfläche (Version 4.3)

Das Dashboard wird die Bedienzentrale: suchen in eigenen Worten, filtern nach Tier, Land und Branche, bewerten per Klick. Claude Code läuft dabei im Hintergrund (SPEC 7.9, 9.9, 13.5, ADR 0004). Was nach welchem Schritt sichtbar ist, steht im BAUPLAN unter „Fahrplan Oberfläche“. Die ersten Teile kommen mit Schritt 5.

## Nächster Schritt

Bauschritt 5: Note, Vergleichsgruppe, Indexstufe, Dashboard.
