## 15. Technische Grundsatzentscheidung

### 15.1 Claude Code oder Claude Agent SDK

Beides, mit klarer Arbeitsteilung.

| Aufgabe | Werkzeug | Grund |
|---|---|---|
| System bauen, testen, erweitern | Claude Code interaktiv | Schnellste Entwicklung, Subagents für parallele Recherche, Hooks für Qualitätsregeln |
| Lauf mit Tiefenanalysen | Python-Orchestrator mit Claude Agent SDK (`claude-agent-sdk`) | Ablauf ist deterministisch steuerbar, Budgets und Zeitlimits je Agent, Schemaprüfung jeder Ausgabe, Wiederholungen ohne Sprachmodell-Entscheidung. Das SDK nutzt dieselben Subagent-Definitionen und Werkzeuge wie Claude Code |
| Ad-hoc-Analyse eines Einzeltitels | Claude Code mit Slash-Befehl `/analyze-stock <ISIN>` (Skill) | Luca kann jederzeit nachfragen und nachbohren |

Ein vollständig vom Sprachmodell gesteuerter Ablauf ("Claude, mach den Lauf") ist für den produktiven Betrieb ungeeignet, weil Reihenfolge, Prüfpflichten und Informationsasymmetrie nicht verlässlich eingehalten würden. Der Orchestrator ist deshalb normaler Python-Code, der Agenten als Funktionen aufruft.

### 15.2 Ausführungsort und Zeitplan

| Option | Vorteile | Nachteile | Empfehlung |
|---|---|---|---|
| Geplante Aufgabe in der Claude-Desktop-App (lokal) | Zugriff auf lokale Dateien | Rechner muss laufen | Für den Start |
| Routine in Claude Code (Cloud, Mindestintervall 1 Stunde) | Läuft ohne eigenen Rechner, Ergebnis als Sitzung einsehbar | Standard-Netzwerkzugang erlaubt nur eine Positivliste. Für `data.sec.gov`, `filings.xbrl.org`, `bafin.de` und Datenanbieter muss die Umgebung auf "Custom" mit eigenen Domains gestellt werden. | Sobald alles stabil läuft |
| GitHub Actions mit Zeitplan | Kostenlos für private Repos im Rahmen, volle Kontrolle über Netzwerk | API-Schlüssel als Secrets | Alternative zur Routine |

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
| Agenten | `claude-agent-sdk`, Subagent-Definitionen als Markdown in `.claude/agents/` |
