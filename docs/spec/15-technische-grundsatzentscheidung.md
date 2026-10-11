## 15. Technische Grundsatzentscheidung

### 15.1 Ausführung über das Claude-Abo

Die Agenten laufen als Subagents in Claude Code und damit über Lucas Claude-Abo. Es gibt keinen Anthropic-API-Schlüssel und keine Abrechnung pro Token. Verbraucht werden die Nutzungslimits des Abos, deshalb die Modellzuordnung nach 8.7 und die Grenzen aus HR-18.

| Aufgabe | Werkzeug | Grund |
|---|---|---|
| System bauen, testen, erweitern | Claude Code interaktiv | Schnellste Entwicklung, Hooks für Qualitätsregeln |
| Universum und Noten | `uv run stockagent screen`, reines Python | Keine Modellaufrufe, beliebig oft wiederholbar |
| Tiefenanalyse | Skill `/analyze-stock <ISIN>` oder `/stockagent` in Claude Code, Subagents nach 8.7, Ablauf vom Python-Zustandsautomaten vorgegeben | Läuft über das Abo, Luca kann jederzeit nachfragen |

**Wer den Ablauf steuert.** Ein vollständig vom Sprachmodell gesteuerter Ablauf hielte Reihenfolge, Prüfpflichten und Informationsasymmetrie nicht verlässlich ein. Deshalb gibt ein Zustandsautomat in Python (`orchestrator.py`) jeden Schritt vor, und Claude Code führt nur aus:

1. `uv run stockagent next <run_id>` liefert den nächsten erlaubten Schritt: welcher Subagent, mit welcher Eingabedatei, wohin die Ausgabe geschrieben wird.
2. Claude Code ruft genau diesen Subagent auf. Die Eingabedatei hat Python erzeugt. J1 bekommt dabei nur Claims ohne Werte (HR-14).
3. Der `SubagentStop`-Hook führt `uv run stockagent accept <run_id> <datei>` aus. Python prüft Schema und alle Gates (12.6) und schreibt den Zustand fort. Eine Ausgabe in falscher Reihenfolge oder mit verletztem Gate wird abgelehnt und geht mit Fehlermeldung zurück (höchstens zweimal, dann `escalated`).
4. Ist der Zustand `done`, rendert Python den Bericht.

Damit bleiben Reihenfolge, Blindheit der Prüfer und Gates in Python erzwungen, auch wenn Claude Code die Aufrufe ausführt. Ein Test spielt einen Lauf mit aufgezeichneten Antworten durch und prüft, dass Schritte außerhalb der Reihenfolge abgelehnt werden.

**Später optional: API-Betrieb.** Für Läufe ohne Luca (Zeitplan) kann derselbe Zustandsautomat die Agenten über das Claude Agent SDK mit API-Schlüssel aufrufen. Das kostet pro Token und wird nur nach Lucas Entscheidung gebaut (19).

### 15.2 Ausführungsort und Zeitplan

| Option | Vorteile | Nachteile | Empfehlung |
|---|---|---|---|
| Start von Hand in Claude Code | Läuft über das Abo, keine Zusatzkosten | Luca startet selbst | Normalfall |
| Geplante Aufgabe in der Claude-Desktop-App (lokal) | Zugriff auf lokale Dateien, über das Abo | Rechner muss laufen | Wenn ein Zeitplan gewünscht ist |
| Routine in Claude Code (Cloud, Mindestintervall 1 Stunde) | Läuft ohne eigenen Rechner, Ergebnis als Sitzung einsehbar | Standard-Netzwerkzugang erlaubt nur eine Positivliste. Für `data.sec.gov`, `filings.xbrl.org`, `bafin.de` und Datenanbieter muss die Umgebung auf "Custom" mit eigenen Domains gestellt werden. | Sobald alles stabil läuft |
| GitHub Actions mit Zeitplan | Kostenlos für private Repos im Rahmen, volle Kontrolle über Netzwerk | braucht API-Betrieb mit Schlüssel und Kosten pro Token | nur nach Entscheidung 19 |

Unabhängig vom Ort startet der Zeitplan immer denselben Befehl `uv run stockagent run --profile scheduled --yes`.

### 15.3 Technologieauswahl

| Bereich | Wahl |
|---|---|
| Sprache | Python 3.12 |
| Paket- und Umgebungsverwaltung | `uv` |
| Datenmodelle und Schemas | Pydantic v2 |
| Datenbank | DuckDB, Spaltendateien als Parquet |
| Datenrahmen | Polars (schnell) mit pandas nur wo Bibliotheken es verlangen |
| SEC-Daten | `edgartools` |
| ESEF-Daten | `xbrl-filings-api`, für Detailauswertung Arelle |
| PDF | Docling, optional LlamaParse |
| Statistik | NumPy, SciPy (Theil-Sen über `scipy.stats.theilslopes`) |
| CLI | Typer |
| Konfiguration | YAML plus Pydantic-Settings, Geheimnisse in `.env` (nie committen) |
| Diagramme | Plotly (Python erzeugt JSON, HTML bindet Plotly.js ein) |
| Tests | pytest, Hypothesis für Formeln, Snapshot-Tests für Berichte |
| Qualität | ruff, mypy im Strict-Modus für `src/stockagent/core` |
| Agenten | Subagents in Claude Code (Markdown in `.claude/agents/`), Ablauf über Python-Zustandsautomat. Optional später `claude-agent-sdk` für API-Betrieb, Gemini CLI für den externen Prüfer |
