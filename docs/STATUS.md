# Projektstand (Übergabe)

Stand: 22.10.2026, Bauschritte bis 11 gebaut, dazu der Anlagehorizont. Diese Datei zuerst lesen, wenn eine neue Sitzung beginnt. Sie wird am Ende jedes Bauschritts aktualisiert.

## Was das System ist

Recherche- und Bewertungssystem für Aktien, die bei Trade Republic handelbar sind. Es zeigt nur an und bewertet. Es gibt keine Orders, keinen Depotzugriff und keine Budget- oder Allokationsplanung. Die Spezifikation liegt in `docs/spec/` (Inhaltsverzeichnis `docs/SPEC.md`), die harten Regeln stehen in `docs/spec/00-arbeitsanweisung.md`.

Luca hält Einzelaktien einige Monate bis etwa 5 Jahre (SPEC 2.1a). Die Note gibt es je Anlagehorizont, Hauptnote ist der Horizont 1 bis 5 Jahre (ADR 0011).

## Arbeitsweise mit Luca

- Vor jedem Bauschritt erklären, was gebaut wird. Am Ende Vorgehen und Ergebnis selbst auf Fehler prüfen und berichten.
- Je Bauschritt ein Branch `schritt-NN-kurzname` und ein Pull Request. Gemergt wird erst nach Lucas Freigabe, nie direkt auf `main`.
- Agenten laufen über Lucas Claude-Abo, nicht über einen API-Schlüssel (`config/models.yaml`, SPEC 8.7).
- Kommunikation auf Deutsch, verständlich ohne Programmierkenntnisse.
- Rechenregel HR-19: jede Berechnung schrittweise über `core/calc.py`, nach jedem Abschnitt ein Prüfpunkt, ein verletzter Prüfpunkt stoppt die Rechnung.

## Erledigt

| Schritt | Inhalt | Pull Request |
|---|---|---|
| 0 bis 3 | Gerüst, Universum, Abschlussdaten USA, Formelregister und Kennzahlen | LucaNiklas/Stock-Agent#2, #3, #7, #9 |
| 4 Teil 1 und 2 | Kursquelle Yahoo, Wechselkurse der EZB, Bewertungskennzahlen | LucaNiklas/Stock-Agent#11, #12 |
| 4 Teil 3a | Zinsen, Damodaran, WACC, Reverse-DCF, normalisiertes EV/EBIT, Altman Z (ADR 0006) | Branch `schritt-04-kapitalkosten` |
| 4 Teil 3b | DCF-Szenarien mit Sensitivität, TTM aus Quartalsberichten | Branch `schritt-04-dcf` |
| 5 | Note, Konfidenz, Risiko, Kategorie, Vergleichsgruppe, Indexstufe, Dashboard (ADR 0007) | Branch `schritt-05-note` |
| 6 | Tiefenanalyse über Subagents, Zustandsautomat, Prüfagenten J1 und J2, Bericht mit 14 Abschnitten (ADR 0008) | Branch `schritt-06-tiefenanalyse` |
| 7 | IFRS über 20-F, ESEF über filings.xbrl.org, Hinterlegungsscheine, Zins GBP (ADR 0009) | Branch `schritt-07-ifrs` |
| 8 | Branchen-Scorecards: Banken, Versicherer, Immobilien, Versorger, Zykliker, Wachstum ohne Gewinn, Holdings als N (ADR 0010) | Branch `schritt-08-scorecards` |
| Horizont | Säule Momentum, Note je Anlagehorizont, Auswahl und Filter im Dashboard (ADR 0011) | Branch `schritt-08-horizont` |
| 9 | Insider aus SEC Form 4, Säule Insider, Agent A6 (ADR 0012) | LucaNiklas/Stock-Agent#21 |
| 10 | Jury J3, Endkontrolle J4, Forensik F1, Eskalationen, Goldstandard, Gemini mit Rückfall (ADR 0013) | LucaNiklas/Stock-Agent#22 |
| 11 | Suche in eigenen Worten, Laufplan, `stockagent run` mit Dialog, Skill `/stockagent`, Dashboard mit Änderungen, Karte, Vergleich, Historie, Methodik, gespeicherte Ansichten (ADR 0014) | Branch `schritt-11-start` |

Die Pull Requests für diese Branches werden gestapelt angelegt und von unten nach oben gemergt.

## Stand der Daten (lokal, nicht im Repository)

Achtung: Die Schritte 2 bis 10 wurden in Cloud-Sitzungen gebaut. Die Daten unten lagen dort. Auf Lucas Mac enthält `data/stockagent.duckdb` (Stand 22.10.2026) nur das Universum aus Schritt 1, Abschlussdaten, Kurse und Noten müssen dort erst geladen werden.

- `data/stockagent.duckdb` (Schema 12, ältere Versionen ab 3 werden beim Öffnen aufgerüstet): 14.509 Aktien. Von 4.021 US-ISINs sind 3.117 einer CIK zugeordnet.
- Abschlusswerte und Kennzahlen für die bisher bewerteten Titel und ihre Vergleichsgruppen (je bis zu 50 Firmen), darunter die Abnahmefirmen der Schritte 2 bis 8.
- Zinsen EUR, USD, GBP, Damodaran-Stand Januar 2026, Wechselkurse der EZB ab 2015.
- `data/raw/`: Rohdateien mit SHA-256.
- `state/`: Lucas Festlegungen (Trade-Republic-Prüfung, SEC-Zuordnung, Damodaran-Branche, Aktien je Hinterlegungsschein, Merkliste, Notizen, Entscheidungen zu Eskalationen in `decisions.yaml`).

## Live geprüft

- Apple: Datenbank und Handrechnung aus den 10-K stimmen bei allen 82 Kennzahlen überein.
- Schritt 7: SAP über das 20-F (50 von 52 Kennzahlen), ASML über ESEF (49 von 52, Note C), Shell, Novartis, Unilever, Diageo, BP. Shell-Nettoverschuldung 45,4 Mrd. USD gegen 45,7 Mrd. USD laut Bericht.
- Schritt 8: Handrechnung aus echten 10-K für JPMorgan (ROTE 19,8 %, Kosten-Ertrags-Verhältnis 52,4 %), Progressive (Schadenquote 66,1 %), Realty Income (FFO 4,27 USD je Aktie), Southern (Dividendendeckung 1,44). Abnahme mit je 3 Firmen je Scorecard läuft (ADR 0010).

## Wichtige Entscheidungen

- ADR 0001: Universum aus den Listen der Deutschen Börse, Handelbarkeit bei Trade Republic prüft Luca selbst.
- ADR 0002: ISIN zu CIK über OpenFIGI und die Tickerliste der SEC.
- ADR 0003: vier Abteilungen mit Quellenkarte, Python holt alles mit fester Adresse.
- ADR 0005: Bewertung auf Anfrage, Vergleichsgruppe 15 bis 50 Titel, Kurse von Yahoo.
- ADR 0006: Kapitalkosten und Reverse-DCF.
- ADR 0007: Note, Konfidenz, Risiko (feste Schwellen bis zum Lauf über das Universum), Kategorie mit Hysterese.
- ADR 0008: Tiefenanalyse über Subagents mit Hooks, Prüfagenten blind, das Sprachmodell darf nur abstufen.
- ADR 0009: IFRS, ESEF, Hinterlegungsscheine.
- ADR 0010: Branchen-Scorecards mit Ersatzgrößen, wo XBRL keine Werte hat.
- ADR 0011: Anlagehorizont, Säule Momentum mit 40 / 15 / 0 Prozent je Horizont.
- ADR 0012: Insider-Signal aus Form 4 als fester Säulenwert, A6 nur bei Geschäften in 24 Monaten.
- ADR 0013: J4 ohne Sprachmodell, Jury aus drei Richtern, F1 nur bei Warnsignal, Goldstandard mit Kandidaten bis zu Lucas Prüfung.
- ADR 0014: Anfrage als festes Schema, Wortliste vor Modell, unbekannte Werte werden abgelehnt, Laufplan mit Grenze 3 Tiefenanalysen und 250 Bewertungen je Lauf.

## Offen und bekannt

- **Deutsche Firmen:** filings.xbrl.org führt keine deutschen Berichte. Nur SAP hat Daten (über das 20-F). Für die übrigen DAX-Werte braucht es eine andere Quelle (Frage an Luca).
- **Zins CHF und DKK:** SNB-Reihen enden im Juli 2025, api.statbank.dk nicht erreichbar. WACC dort unknown.
- **Hinterlegungsscheine ohne Verhältnis im Börsennamen** (Philips, ASML NY, Ericsson): Festlegung in `state/adr_verhaeltnis.yaml` nötig.
- **Banken und Versicherer:** CET1, notleidende Kredite, Combined Ratio und Solvency-Quote stehen nicht in XBRL. Ersatz siehe ADR 0010.
- **Tiefenanalyse:** `claude -p` und die Hooks in den Agent-Dateien sind auf Lucas Mac noch nicht getestet. Zeitlimit 60 Minuten statt 20 laut SPEC.
- **Goldstandard:** 21 Kandidaten in `eval/kandidaten/`, Luca prüft sie und verschiebt sie nach `eval/gold/`. J2 ist noch nicht offiziell aufgezeichnet (Live-Lauf auf dem Mac), A3 bis A9 und J3 haben noch keine Goldfälle. `eval/gold/README.md` ist noch der Platzhaltertext, der Ordner ist für Agenten gesperrt.
- **Gemini:** nicht getestet, `extern.aktiv` aus. Test auf dem Mac mit `stockagent tool gemini-test`.
- **BaFin-Insider:** `portal.mvp.bafin.de` in der Cloud-Umgebung gesperrt.
- **Momentum:** Kursreaktion auf Berichte als Rohrendite ohne Marktindex, Gewinnüberraschungen gegen Analystenschätzungen fehlen (keine Quelle).
- **PDF-Rückfall mit Docling und A2** (SPEC 7.4) nicht gebaut.
- **Mehrfachlistings:** Zusammenführung über die LEI für die Emittentensuche gebaut, im Dashboard noch je Listing eine Zeile.
- **Schritt 11 nicht gebaut:** Chancen-Karte, Themen ohne Branchencode (A0), Abo-Verbrauch aus `log.jsonl`, Neuanalyse statt Wiederholung (SPEC 9.4). Stil „Turnaround“ abgelehnt, bis Luca ein Merkmal festlegt (ADR 0014).
- **Claude Code auf Lucas Mac:** `claude` ist im Terminal nicht gefunden (nur die Desktop-App). Ohne den Befehl gehen Tiefenanalyse und Übersetzen freier Sätze über das Modell nicht, Wortliste, Filter und Noten schon. Das Dashboard zeigt einen Hinweis.

## Wichtige Befehle

```bash
uv run stockagent app                       # Dashboard (Doppelklick: Stockagent.command)
uv run stockagent bewerten <ISIN>           # Note je Horizont, Vergleichsgruppe wird geladen
uv run stockagent screen --horizont kurz --note A,B
uv run stockagent analyze <ISIN>            # Tiefenanalyse (in Claude Code: /analyze-stock)
uv run stockagent sec update --isin <ISIN> | esef update -i <ISIN> | prices update -i <ISIN>
uv run stockagent metrics show <ISIN> --rechenweg <id>
uv run pytest && uv run ruff check . && uv run mypy
```

## Nächster Schritt

1. PR für Schritt 11 (Branch `schritt-11-start`): CI abwarten, mergen nach Lucas Freigabe.
2. Auf Lucas Mac Daten laden (Lucas Vorgabe 22.10.2026: nach Schritt 11): `sec update`, `markt update`, `fx update`, dann Abnahmefirmen bewerten, Abnahme Schritt 8 abschließen (Ergebnisse in ADR 0010).
3. Claude Code für das Terminal installieren, dann auf dem Mac: `stockagent tool gemini-test`, `eval/run_eval.py --live` (Aufzeichnung einchecken), eine Tiefenanalyse mit `/analyze-stock`, `/review-escalations` und `/stockagent` ausprobieren.
4. Danach Bauschritt 12 (optional): Zeitplan, braucht Lucas Entscheidung zu API-Schlüssel und Kosten.

Fragen an Luca (gesammelt): BaFin-Domain `portal.mvp.bafin.de` freigeben, Abdeckung DAX,
CHF/DKK-Kurse, ADR-Verhältnisse (Philips, ASML NY, Ericsson), Zeitlimit 60 statt 20 Minuten,
Goldkandidaten prüfen, Beneish-Kappung nach Entkräftung durch F1 aufheben oder nicht (ADR 0013),
Merkmal für den Stil „Turnaround“ und Grenzen je Lauf (ADR 0014).
