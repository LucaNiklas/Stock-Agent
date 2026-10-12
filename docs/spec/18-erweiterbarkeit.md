## 18. Erweiterbarkeit

Das System ist so gebaut, dass Erweiterungen an definierten Stellen andocken.

### 18.1 Neue Kennzahl

1. Eintrag in `config/metrics.yaml` (ID, Formel, Eingaben, Version, Sektorhinweise).
2. Funktion in `core/registry.py`, registriert über den Dekorator `@metric("id")`, gerechnet über den Rechenweg aus `core/calc.py` mit den Prüfpunkten aus dem Registereintrag (12.7, HR-19).
3. Test mit Handrechnung.
4. Falls im Score verwendet, Gewicht in `scoring.yaml`, Changelog-Eintrag, `methodology_version` erhöhen.

### 18.2 Neue Datenquelle

Klasse in `data/sources/`, die das Protokoll `DataSource` erfüllt (`fetch(lei, since) -> list[Fact]`, `name`, `priority`). Eintrag in `sources.yaml`. Die Datenqualitätsprüfung behandelt sie automatisch als zusätzliche Quelle.

### 18.3 Neuer Agent

Vorlage in `agents_src/` (daraus erzeugt `stockagent render-agents` die Datei in `.claude/agents/`), Prompt in `prompts/`, Ein- und Ausgabeschema in `schemas/`, Eintrag im Ablauf von `orchestrator.py`, Goldstandard-Fälle in `eval/`.

### 18.4 Geplante Erweiterungen

| Erweiterung | Nutzen | Aufwand |
|---|---|---|
| Vollständige Normalisierung weiterer Standards (J-GAAP, Ind AS, HGB-Konzern) | Konfidenz K2 auch für diese Unternehmen | mittel je Standard |
| Weitere Scorecards (Biotech mit Pipeline-Bewertung, Rohstoffförderer mit Reserven) | genauere Noten in Sonderbranchen | mittel |
| Transkripte von Analystenkonferenzen | Ton und Aussagen des Managements im Zeitverlauf | mittel, Datenquelle meist kostenpflichtig |
| Konsensschätzungen | Vergleich implizites Wachstum mit Analystenerwartungen | Datenkosten |
| Nachhaltigkeitsdaten aus ESRS-Berichten (CSRD) | Markierung nach Lucas Werten, ohne Einfluss auf die Note | mittel |
| Weitere Länder bei Insider-Daten | Signal für mehr EU-Titel | je Land klein |
| Lernende Gewichte | erst nach 3 Jahren Notenkontrolle und nur mit getrennter Testperiode | hoch, Risiko der Überanpassung |
| Eigener MCP-Server | Werkzeuge in jeder Claude-Oberfläche | klein |

### 18.5 Versionierung

Jede Ausgabe trägt `methodology_version`, `agent_version`, `prompt_hash` und `model`. Ergebnisse unterschiedlicher Methodik-Versionen werden im Dashboard nie ohne Hinweis verglichen.
