# Stock-Agent

Privates Recherche- und Bewertungssystem für Aktien, die bei Trade Republic handelbar sind. Es **zeigt und bewertet** nur: keine Orders, kein Depotzugriff, keine Budget- oder Allokationsplanung. Recherche-Grundlage, keine Anlageberatung.

## Stand

Fertig sind Gerüst (Schritt 0) und Aktienuniversum (Schritt 1): 14.509 Aktien der Deutschen Börse mit ISIN, WKN, LEI, Hauptsitz und Rechtssitz. Was als Nächstes kommt, steht in [docs/STATUS.md](docs/STATUS.md), der vollständige Plan in [docs/BAUPLAN.md](docs/BAUPLAN.md).

## Einrichten

Voraussetzungen: macOS mit [uv](https://docs.astral.sh/uv/) und Git.

```bash
uv sync
uv run stockagent universe update
```

Der erste Abruf lädt die Listen der Deutschen Börse und die GLEIF-Daten und dauert etwa 2 Minuten. Die Daten liegen danach lokal in `data/` und nicht im Repository.

## Wichtigste Befehle

| Befehl | Wirkung |
|---|---|
| `uv run stockagent universe update [--refresh] [--force]` | Aktienliste und Länder neu laden (höchstens wöchentlich) |
| `uv run stockagent universe show --suche siemens` | Aktien im Terminal suchen |
| `uv run stockagent universe serve` | durchsuchbare Übersicht im Browser |
| `uv run stockagent tr-check <ISIN> ja\|nein` | eigene Prüfung in der Trade-Republic-App festhalten |
| `uv run pytest && uv run ruff check . && uv run mypy` | Tests und Prüfungen |

## Aufbau

| Ort | Inhalt |
|---|---|
| `docs/` | Spezifikation (`spec/`, Inhaltsverzeichnis `SPEC.md`), Projektstand `STATUS.md`, Bauplan `BAUPLAN.md`, Entscheidungen `adr/` |
| `src/stockagent/` | Programmcode. `core/` rechnet, `data/` holt und speichert Daten, `gates/` prüft Agentenausgaben |
| `config/` | alle Schwellen, Gewichte, Quellen und die Modellwahl je Agent |
| `tests/` | automatische Tests, laufen bei jedem Pull Request |
| `.claude/` | Einstellungen, Hooks und Skills für Claude Code |

Dateien mit „PLATZHALTER“ im Kopf werden erst in einem späteren Bauschritt gefüllt. Wann und womit, steht im Kopf der Datei und in `docs/BAUPLAN.md`.
