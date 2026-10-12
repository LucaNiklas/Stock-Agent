# Projektstand (Übergabe)

Stand: 11.10.2026, nach Bauschritt 1. Diese Datei zuerst lesen, wenn eine neue Sitzung beginnt. Sie wird am Ende jedes Bauschritts aktualisiert.

## Was das System ist

Recherche- und Bewertungssystem für Aktien, die bei Trade Republic handelbar sind. Es zeigt nur an und bewertet. Es gibt keine Orders, keinen Depotzugriff und keine Budget- oder Allokationsplanung. Die Spezifikation liegt in `docs/spec/` (Inhaltsverzeichnis `docs/SPEC.md`, Version 4.1), die harten Regeln stehen in `docs/spec/00-arbeitsanweisung.md`.

## Arbeitsweise mit Luca

- Vor jedem Bauschritt erklären, was gebaut wird. Am Ende Vorgehen und Ergebnis selbst auf Fehler und Verbesserungen prüfen und das Ergebnis berichten.
- Je Bauschritt ein Branch `schritt-NN-kurzname` und ein Pull Request. Gemergt wird erst nach Lucas Freigabe, nie direkt auf `main` pushen.
- Agenten laufen später über Lucas Claude-Abo, nicht über einen API-Schlüssel. Haiku sucht und sammelt, Sonnet schreibt und prüft, Opus nur für die anspruchsvollsten Schritte (`config/models.yaml`, SPEC 8.7). Gemini ist ein optionaler Prüfer, sein Test kommt in Schritt 10.
- Kommunikation auf Deutsch.
- **Rechenregel (HR-19, Lucas Vorgabe):** Jede Berechnung läuft schrittweise. Nach jedem Abschnitt wird das bisher Gerechnete mit einem Prüfpunkt kontrolliert, erst dann geht es weiter. Ein verletzter Prüfpunkt stoppt die Rechnung. Details in SPEC 12.7, gebaut als `core/calc.py` zu Beginn von Bauschritt 3, genutzt in den Schritten 3, 4, 5 und 7.

## Erledigt

| Schritt | Inhalt | Pull Request |
|---|---|---|
| Spezifikation 4.0/4.1 | Umfang nur Anzeigen und Bewerten, Bauschritte statt Phasen, Ausführung über das Abo, Modell je Agent | LucaNiklas/Stock-Agent#1 |
| 0 Gerüst | uv, CI, Grundtypen (`Money`, `Fact`, `FreeText`, `Claim`), Gates, CLI-Gerüst, Hooks, `render_agents.py` | LucaNiklas/Stock-Agent#2 |
| 1 Universum | Aktienliste der Deutschen Börse, LEI und Länder aus der GLEIF, Lucas Trade-Republic-Prüfungen, Anzeige im Terminal und als HTML | LucaNiklas/Stock-Agent#3 (gemergt 11.10.2026) |

## Stand der Daten (lokal, nicht im Repository)

- `data/stockagent.duckdb` (Schema-Version 3): 14.509 Aktien, Stand der Quelle 12.10.2026. LEI bei 8.373, Hauptsitz laut GLEIF bei 8.102, 39 widersprüchlich, 6.368 nur ISIN-Land. 1.540 Hinterlegungsscheine.
- `data/raw/`: Rohdateien mit SHA-256. GLEIF-Dateien werden nach 2 Ständen aufgeräumt.
- `state/tr_checks.yaml`: Lucas Prüfungen in der Trade-Republic-App. Noch leer.
- Die Datenbank fehlt nach einem frischen Klonen. Neu aufbauen mit `uv run stockagent universe update` (etwa 2 Minuten).

## Wichtige Befehle

```bash
uv run stockagent universe update [--refresh] [--force]
uv run stockagent universe show --suche siemens
uv run stockagent universe html --open
uv run stockagent tr-check <ISIN> ja|nein
uv run pytest && uv run ruff check . && uv run mypy
```

## Wichtige Entscheidungen

- ADR 0001 (`docs/adr/0001-universum-quelle.md`): Die Trade-Republic-Produktübersicht liegt hinter dem AWS-WAF-Bot-Schutz und wird nicht automatisch abgerufen. Basis sind deshalb die Listen der Deutschen Börse, und die Handelbarkeit prüft Luca selbst. finanzen.net verbietet automatisierte Abfragen und dient nur als Stichprobe von Hand.
- Länder: Hauptsitz und Rechtssitz (Rechtsordnung) laut GLEIF, nur wenn der Name passt und kein Widerspruch zur ISIN besteht. Sonst wird das ISIN-Land als unsicher markiert.
- Keine Order-Sperre nötig (Lucas Entscheidung). HR-09 ist eine Umfangsregel.

## Offen und bekannt

- **Branche und Kernprodukt fehlen noch.** US-Emittenten: SIC-Code und Geschäftsbeschreibung aus der SEC (Schritt 2). Übrige: SPEC 7.8 (Wikidata, dann Lucas Bestätigung).
- **Mehrfachlistings:** Ein Unternehmen erscheint mehrfach (Stammaktie, ADR, CDR). Die Zusammenführung über die LEI folgt mit den Abschlussdaten.
- **Länder ohne LEI (6.368 Aktien):** nur das ISIN-Land, unsicher. Für SEC-Melder (auch ausländische mit 20-F) liefert die SEC in Schritt 2 Geschäftsadresse und Gründungsstaat.
- **Unsicherheit bei Umbenennungen:** Wurde ein Unternehmen umbenannt und führt die GLEIF noch den alten Namen, fällt das Land auf das ISIN-Land zurück (232 Fälle).
- Das Feld „Primary Market MIC Code“ der Deutschen Börse ist kein verlässlicher Primärmarkt und darf nicht als Kursquelle dienen.
- Ein kommerzieller Datenanbieter ist nicht entschieden (SPEC 19 Nr. 1). Er wird spätestens für Kurse in Schritt 4 nötig.

## Danach

Bauschritt 3 beginnt mit dem Rechenweg `core/calc.py` und dem Prüfpunkt-Katalog CP-01 bis CP-08 (SPEC 12.7), bevor die erste Kennzahl gebaut wird.

## Nächster Schritt

Bauschritt 2 „Abschlussdaten USA“ (SPEC 16.10, Abschnitte 3.2, 7.2, 7.5 bis 7.7): SEC-Anbindung (`edgartools`, User-Agent mit Lucas Name und E-Mail in `.env` als `SEC_USER_AGENT`), DuckDB-Tabellen `documents` und `facts`, `pit_query(as_of=...)`, Datenqualität 3.2. Dazu SIC-Code, Geschäftsbeschreibung und Adresse der SEC für die Branchen- und Länderdaten. Prompt-Vorlage: SPEC 17.3.
