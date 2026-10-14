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

### 18.6 Teilen und Unabhängigkeit von Claude

Lucas Ziel (14.10.2026): Die Plattform dient zuerst ihm, später jedem, der sie nutzen will. Dass dafür vorerst Claude nötig ist, ist in Ordnung. Am Ende soll sie aber alle Funktionen auch ohne Claude bieten. Beides kommt nach Schritt 12 (BAUPLAN, Bausteine F und G). Damit der Weg dorthin offen bleibt, gelten ab sofort fünf Regeln.

1. Alles Deterministische bleibt in Python ohne Sprachmodell: Datenabruf mit fester Adresse, Datenqualität, Kennzahlen, Trends, Scores, Bewertung, Note und die Hinweise an die Agenten. Das läuft schon heute bei jedem, der das Repository klont.
2. Agenten werden nur über eine Schnittstelle aufgerufen, nie direkt über ein bestimmtes Werkzeug. Auftrag und Antwort sind Schemas (8.4, 8.10). Hinter der Schnittstelle kann Claude Code über ein Abo, die Claude-API, ein anderes Modell oder ein lokales Modell stehen.
3. Persönliches liegt nur in `state/` und in Umgebungsvariablen (SEC-User-Agent, Schlüssel), nie im Code oder in `config/`.
4. Nur frei zugängliche Datenquellen sind Pflicht. Kostenpflichtige Anbieter (SPEC 19 Nr. 1) bleiben optional.
5. Jede Agentenaufgabe hat Fälle im Goldstandard (11.6). So lässt sich messen, ob ein Ersatzmodell gut genug ist, bevor es Claude ablöst.
