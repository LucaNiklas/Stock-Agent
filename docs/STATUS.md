# Projektstand (Übergabe)

Stand: 13.10.2026, nach Bauschritt 2. Diese Datei zuerst lesen, wenn eine neue Sitzung beginnt. Sie wird am Ende jedes Bauschritts aktualisiert.

## Was das System ist

Recherche- und Bewertungssystem für Aktien, die bei Trade Republic handelbar sind. Es zeigt nur an und bewertet. Es gibt keine Orders, keinen Depotzugriff und keine Budget- oder Allokationsplanung. Die Spezifikation liegt in `docs/spec/` (Inhaltsverzeichnis `docs/SPEC.md`, Version 4.1), die harten Regeln stehen in `docs/spec/00-arbeitsanweisung.md`.

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

## Stand der Daten (lokal, nicht im Repository)

- `data/stockagent.duckdb` (Schema-Version 4, ältere Version 3 wird beim Öffnen ohne Datenverlust aufgerüstet): 14.509 Aktien, Stand der Quelle 12.10.2026.
- Zuordnung zur SEC (Lauf vom 13.10.2026): von 4.021 US-ISINs sind 3.117 einer CIK zugeordnet (3.052 verschiedene Firmen), 9 unsicher, 895 ohne SEC-Melder (davon 845 Hinterlegungsscheine, meist nicht gesponserte ADRs, 69 davon nur ADR-Registrierungen der Depotbank). Stammdaten liegen für alle 3.052 vor. Die SEC selbst führt bei 115 keinen SIC-Code (überwiegend geschlossene Fonds) und bei 2 keine Geschäftsadresse. 2.697 haben eine US-Geschäftsadresse.
- Die 9 unsicheren Zuordnungen zeigt `stockagent sec show <ISIN>` mit Grund (meist Umbenennungen wie Hypera/Hypermarcas oder Verwechslungen bei OpenFIGI wie Helix Energy mit dem Ticker von Hornbeck Offshore). Festlegen mit `stockagent sec map <ISIN> <CIK>|keine`.
- Abschlusswerte und Prüfungen bisher für die 10 Abnahmefirmen: Apple, Microsoft, Coca-Cola, Johnson & Johnson, Caterpillar, Procter & Gamble, Nike, Walmart, JPMorgan, PagerDuty. Alle erfüllen die Bilanzgleichung für zehn Jahre, alle verfügbaren Kernwerte stimmen auf dem zweiten Weg mit dem Originalbericht überein.
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
uv run pytest && uv run ruff check . && uv run mypy
```

## Wichtige Entscheidungen

- ADR 0001 (`docs/adr/0001-universum-quelle.md`): Die Trade-Republic-Produktübersicht liegt hinter dem AWS-WAF-Bot-Schutz und wird nicht automatisch abgerufen. Basis sind deshalb die Listen der Deutschen Börse, und die Handelbarkeit prüft Luca selbst. finanzen.net verbietet automatisierte Abfragen und dient nur als Stichprobe von Hand.
- Länder: Hauptsitz und Rechtssitz (Rechtsordnung) laut GLEIF, nur wenn der Name passt und kein Widerspruch zur ISIN besteht. Sonst wird das ISIN-Land als unsicher markiert.
- Keine Order-Sperre nötig (Lucas Entscheidung). HR-09 ist eine Umfangsregel.
- ADR 0002: ISIN zu CIK über OpenFIGI und die Tickerliste der SEC, Unsicheres bleibt leer. onvista und finanzen.net werden nicht automatisch abgefragt.
- ADR 0003: vier Abteilungen (Recherche, Berechnung, Auswertung, Prüfung) mit Quellenkarte. Python holt alles mit fester Adresse, Agenten suchen nur, wo es keine gibt.
- Werte für Abschlusszahlen nur für eine Auswahl laden, alle US-Firmen erst in Schritt 5 (Lucas Entscheidung 13.10.2026).

## Offen und bekannt

- **Geschäftsbeschreibung fehlt noch.** Die SEC liefert sie nicht strukturiert (Feld `description` leer). Sie kommt in Schritt 5 aus Item 1 des 10-K. SIC-Codes liegen für alle zugeordneten SEC-Melder vor. Übrige: SPEC 7.8 (Wikidata, dann Lucas Bestätigung).
- **Mehrfachlistings:** Ein Unternehmen erscheint mehrfach (Stammaktie, ADR, CDR). Die Zusammenführung über LEI und CIK ist vorbereitet (`issuers.lei`, `issuers.cik`), aber noch nicht gebaut.
- **Länder ausländischer SEC-Melder:** Die SEC nennt ihr Land nur als eigenen Code (etwa `2M` für Deutschland). Gespeichert sind Code und Name. Eine Abbildung auf ISO-Codes fehlt noch.
- **Länder ohne LEI (6.368 Aktien):** nur das ISIN-Land, unsicher. Für zugeordnete SEC-Melder liegt jetzt die Geschäftsadresse vor.
- **Unsicherheit bei Umbenennungen:** Führt die GLEIF noch den alten Namen, fällt das Land auf das ISIN-Land zurück (232 Fälle).
- **Finanzschulden:** Ein Gesamtkonzept melden nur wenige Firmen. Die Summe aus kurz- und langfristigen Teilen bildet Schritt 3 (`financial_debt_teile` in `config/concept_map.yaml`).
- **Zweite unabhängige Quelle:** Der zweite Weg ist das XBRL des Originalberichts. Ein kommerzieller Anbieter fehlt (SPEC 19 Nr. 1), spätestens für Kurse in Schritt 4 nötig.
- **Vorzugsaktien und Anleihen im Universum:** Die Deutsche Börse führt einige Vorzugsaktien und nachrangige Anleihen als `CS` (etwa „HANCOCK WHITNEY SU.NTS 25“). Sie werden dem richtigen Emittenten zugeordnet, sind aber keine Stammaktie. Bereinigung des Universums offen.
- **Gelöschte Handzuordnung:** Entfernt Luca einen Eintrag aus `state/cik_overrides.yaml`, gilt die alte Zuordnung bis zur nächsten Neuprüfung (90 Tage). Sofort wirkt `sec map <ISIN> <CIK>`.
- **HR-06 Architekturtest** (`test_arithmetic_only_in_core`) fehlt noch. Bisher eingehalten durch Code-Review, `core/dq.py` rechnet alle Prüfungen.
- Das Feld „Primary Market MIC Code“ der Deutschen Börse ist kein verlässlicher Primärmarkt und darf nicht als Kursquelle dienen.

## Nächster Schritt

Bauschritt 3 „Formelregister und Kennzahlen“ (SPEC 3.3 bis 3.5, 12.2, 12.7, 18.1): Kennzahlen in `config/metrics.yaml` und `core/registry.py` über den Rechenweg aus `core/calc.py`, Trends in `core/trends.py`, Scores in `core/scores.py`. Jede Kennzahl mit Handrechnung aus einem echten 10-K (die drei Firmen aus `tests/test_sec_abnahme.py` bieten sich an). Aktienzahlen um Splits bereinigen (DQ-08 erkennt sie schon). Skill `/add-metric` nutzen.
