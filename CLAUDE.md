# stockagent

Recherche-System für Einzelaktien. Vollständige Spezifikation in docs/SPEC.md. Bei Widersprüchen gilt SPEC.md.

## Unverhandelbare Regeln
Die harten Regeln HR-01 bis HR-16 stehen in docs/SPEC.md Abschnitt 0.1. Lies sie zu Beginn jeder Sitzung.
- Sprachmodelle liefern nie Zahlen. Formeln nur in src/stockagent/core/registry.py.
- Jeder Wert braucht Quelle (doc_hash+page oder XBRL-Konzept+Periode), Währung, Einheit, Standard, Periode.
- Point-in-Time über store.pit_query(as_of=...).
- Keine Order-Funktionen, kein Schreibzugriff auf Broker.
- Schwellen, Gewichte und Modellzuordnung nur in config/.
- Prüfagenten sehen geprüfte Werte erst nach eigenem Ergebnis.
- Nie direkt auf main pushen. Branch je Phase, Pull Request, CI grün.
- Wenn etwas unklar ist, frag nach statt zu raten.

## Befehle
- uv run pytest            Tests
- uv run ruff check . && uv run mypy src
- uv run stockagent run [--profile scheduled --yes]
- uv run stockagent review-holdings
- uv run stockagent analyze <ISIN>
- uv run python scripts/render_agents.py   Agent-Dateien aus agents_src/ erzeugen
- uv run python eval/run_eval.py   Goldstandard

## Konventionen
- Neue Kennzahl: Eintrag in config/metrics.yaml, Funktion in core/registry.py, Test mit Handrechnung aus echtem Bericht.
- Jede Methodikänderung: Eintrag in docs/METHODOLOGY_CHANGELOG.md, methodology_version erhöhen.
- Prompts versioniert in src/stockagent/agents/prompts/, Änderung erfordert eval-Lauf.
