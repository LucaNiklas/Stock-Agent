# Stock-Agent

Privates Recherche- und Bewertungssystem für Aktien, die bei Trade Republic handelbar sind. Es **zeigt und bewertet** nur: keine Orders, kein Depotzugriff, keine Budget- oder Allokationsplanung. Recherche-Grundlage, keine Anlageberatung. „Attraktiv“ ist eine Einordnung, keine Empfehlung.

## Was es kann

- **Universum:** 14.509 Aktien der Börse Frankfurt und von Xetra mit ISIN, WKN, LEI und Hauptsitz. Ob eine Aktie bei Trade Republic handelbar ist, hältst du selbst fest.
- **Note je Aktie** ohne Sprachmodell: Kennzahlen aus den Berichten bei der SEC (USA, 20-F) und ESEF (Europa), Kurse von Yahoo, Wechselkurse der EZB. Daraus Note A bis E im Vergleich mit 15 bis 50 ähnlichen Firmen, dazu Konfidenz K1 bis K4, Risiko R1 bis R5 und Kategorie. Die Note gibt es je Anlagehorizont, Hauptnote ist der Horizont 1 bis 5 Jahre. Jede Zahl hat einen Rechenweg mit Prüfpunkten und eine Quelle.
- **Tiefenanalyse** eines Unternehmens über Claude-Agenten mit deinem Claude-Abo: finanzieller Überblick mit 14 Abschnitten, jede Aussage mit Beleg, geprüft von Prüfagenten. Was die Prüfer nicht freigeben, landet bei dir als Eskalation.
- **Dashboard** im Browser: Suche in eigenen Worten („Tier 1 Aktien aus Griechenland, Branche Automobil, bewerte sie“), Filter, Laufplan vor jedem Lauf, Änderungen, Karte Branche mal Land, Vergleich, Historie, Methodik, Eskalationen.
- **Zeitplan** (optional): täglicher Lauf über deine Beobachtungsliste ohne Modellkosten, mit Benachrichtigung.

## Einrichten (einmalig)

Voraussetzungen: macOS, [uv](https://docs.astral.sh/uv/), Git und für die Tiefenanalyse [Claude Code](https://claude.com/claude-code) mit deinem Claude-Abo.

```bash
uv sync
cp .env.example .env    # dann SEC_USER_AGENT mit Name und E-Mail eintragen
uv run stockagent universe update
uv run stockagent sec update
uv run stockagent markt update
uv run stockagent fx update
```

- `universe update` lädt die Listen der Deutschen Börse und die GLEIF-Daten (etwa 2 Minuten).
- `sec update` ordnet alle US-Aktien ihrer SEC-Nummer zu und lädt die Stammdaten (30 bis 60 Minuten, wegen der Ratenbegrenzung von OpenFIGI und SEC). Ohne diesen Schritt gibt es keine Vergleichsgruppen. `bewerten` holt ihn bei Bedarf selbst nach.
- `markt update` lädt Zinsen und die Daten von Damodaran, `fx update` die Referenzkurse der EZB.
- Claude Code installieren und einmal anmelden: `curl -fsSL https://claude.ai/install.sh | bash`, danach `~/.local/bin/claude` starten und mit dem Claude-Konto anmelden.

Die Daten liegen lokal in `data/` und nicht im Repository. Deine Festlegungen (Beobachtungsliste, Notizen, Trade-Republic-Prüfungen, Entscheidungen zu Eskalationen, gespeicherte Ansichten) liegen in `state/`.

## Starten

Doppelklick auf `Stockagent.command` im Projektordner, oder:

```bash
uv run stockagent app
```

Das Dashboard läuft unter http://127.0.0.1:8765 und ist nur auf diesem Rechner erreichbar. Der erste Klick auf „Bewerten“ lädt Daten für die Aktie und ihre Vergleichsgruppe und kann einige Minuten dauern, danach geht es schneller.

## Wichtigste Befehle

| Befehl | Wirkung |
|---|---|
| `uv run stockagent app` | Dashboard starten |
| `uv run stockagent bewerten <ISIN>` | Note, Konfidenz, Risiko und Kategorie einer Aktie |
| `uv run stockagent anfrage "Satz"` | Satz in einen Filter übersetzen und Treffer zählen |
| `uv run stockagent run` | Lauf über eine Kategorie: Fragen, Laufplan, Bestätigung |
| `uv run stockagent screen [--note A,B]` | bewertete Titel als Tabelle |
| `uv run stockagent analyze <ISIN>` oder `/analyze-stock <ISIN>` in Claude Code | Tiefenanalyse |
| `uv run stockagent eskalationen` oder `/review-escalations` | eskalierte Analysen ansehen und entscheiden |
| `uv run stockagent zeitplan an` und `zeitplan einrichten --laden` | täglichen Lauf um 07:30 einrichten |
| `uv run stockagent dashboard --html stand.html` | Dashboard als einzelne Datei zum Ansehen und Teilen (Lesemodus) |
| `uv run stockagent tr-check <ISIN> ja\|nein` | Handelbarkeit bei Trade Republic festhalten |

Alle Befehle mit Optionen stehen in `CLAUDE.md` und mit `uv run stockagent --help`.

## Wenn etwas nicht geht

- **Note N „Vergleichsgruppe zu klein“:** Die Zuordnung der US-Aktien fehlt oder ist unvollständig: `uv run stockagent sec update`.
- **„nicht erreichbar nach 5 Versuchen“:** Das Internet war weg, etwa weil der Mac schlief. Den Befehl wiederholen, Geladenes bleibt erhalten. Bei langen Läufen hält `caffeinate -i uv run stockagent ...` den Mac wach.
- **Tiefenanalyse startet nicht, „Claude Code nicht gefunden“:** Claude Code installieren und einmal anmelden (siehe oben).
- **`permission denied: ~/.zshrc`:** Die Datei gehört dem Systemkonto root. Einmal `sudo chown $(whoami) ~/.zshrc` ausführen, danach lässt sie sich ändern.
- **Dashboard meldet „Datenbank gesperrt“:** Ein anderer Befehl läuft gerade, etwa ein Lauf nach Zeitplan. Warten, bis er fertig ist.

## Aufbau

| Ort | Inhalt |
|---|---|
| `docs/` | Spezifikation (`spec/`, Inhaltsverzeichnis `SPEC.md`), Projektstand `STATUS.md`, Bauplan `BAUPLAN.md`, Entscheidungen `adr/`, Änderungen der Methodik `METHODOLOGY_CHANGELOG.md` |
| `src/stockagent/` | Programmcode. `core/` rechnet (nur dort gibt es Arithmetik), `data/` holt und speichert Daten, `gates/` und `judges/` prüfen Agentenausgaben, `dashboard/` ist die Oberfläche |
| `config/` | alle Schwellen, Gewichte, Quellen, Wortliste und die Modellwahl je Agent |
| `agents_src/`, `.claude/` | Vorlagen der Agenten, Skills und Hooks für Claude Code |
| `tests/` | automatische Tests, laufen bei jedem Pull Request |
| `state/` | deine Festlegungen |

## Entwicklung

```bash
uv run pytest && uv run ruff check . && uv run mypy src
```

Gebaut wird in Schritten mit je einem Branch und Pull Request, nie direkt auf `main`. Den Stand und den nächsten Schritt nennt `docs/STATUS.md`.
