# ADR 0008: Tiefenanalyse mit Zustandsautomat (Bauschritt 6)

Status: angenommen (20.10.2026, im Rahmen von Lucas Auftrag „bis Bauschritt 8 in einem Durchlauf,
beste Option wählen“). Abweichungen von der Spezifikation sind unten einzeln benannt.

## Kontext

SPEC 15.1 legt fest: Python gibt den Plan vor, Claude Code führt nur aus. Die Agenten laufen als
Subagents über Lucas Abo. Geprüft wurde vor dem Bau die aktuelle Dokumentation von Claude Code
(Oktober 2026): Subagents unterstützen im Frontmatter `tools`, `disallowedTools`, `model`,
`maxTurns` und `hooks`. Ein `Stop`-Hook im Frontmatter wird zum `SubagentStop`-Hook und bekommt
die letzte Antwort des Subagents als `last_assistant_message`. Exit-Code 2 schickt eine Meldung an
den Subagent zurück, der dann weiterarbeitet. `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` verhindert
verschachtelte Subagents. `claude -p "/analyze-stock <ISIN>"` ruft den Skill auch ohne Terminal auf.

## Entscheidung

1. **Plan je Lauf** (`orchestrator.py`):
   A1 je Hinweis an A1, dann A3 und A4 parallel, A5, A7, Erwiderung A3E, J1 und J2 parallel, A9,
   dann Entscheidung und Bericht. Nachforderungen von A3, A4 oder A5 erzeugen einen A1-Auftrag
   und danach einen zweiten Auftrag desselben Fachs (eine Runde).
2. **Annahme** (`stockagent accept`): aus dem Stop-Hook des Subagents
   (`scripts/hooks/annehmen.sh`). Zusätzlich kann die Hauptsitzung die Antwort als Datei übergeben,
   falls der Hook nicht läuft. Eine Antwort für einen nicht beauftragten Auftrag wird abgelehnt
   (Reihenfolge). Harte Schranken (Schema, Zahlen, Formulierung, Konsistenz) schicken die Antwort
   zurück, nach zwei Wiederholungen ist der Auftrag eskaliert. Nicht wörtliche Zitate und fehlende
   Belege gehen ebenfalls zurück. Beim letzten Versuch wird die Antwort ohne die betroffenen
   Claims angenommen (INC-14).
3. **Umschlag** (Lauf, Agent, Version, Prompt-Hash, Modell) setzt Python bei der Annahme, nicht
   der Agent.
4. **Berichte als Seitentext:** Das Hauptdokument der letzten zwei Jahresberichte holt Python bei
   der SEC (feste Adresse). Es wird an den Seitenumbrüchen der HTML-Datei geteilt
   (Tabelle `document_pages`). Die Seiten liegen zusätzlich als Dateien unter
   `runs/<run_id>/dokumente/`, damit Agenten nur mit Read und Grep arbeiten. *Abweichung:* Die
   Seitenzahl ist die laufende Seite im Dokument, nicht die aufgedruckte Nummer.
5. **Werkzeugrechte** im Frontmatter: Recherche (A1) hat Web, aber kein Bash, Write oder Edit
   (HR-17). Auswertung und Prüfung haben kein Web. Bash nur für A3, A7 und J1, und ein
   PreToolUse-Hook (`scripts/hooks/nur_werkzeuge.sh`) lässt nur
   `uv run stockagent tool rechenweg|nachrechnen` durch. Kein Agent hat das Werkzeug `Agent`.
6. **J1 blind:** Die Eingabe enthält nur Referenzen (`metric_id@periode`), keine Werte und keinen
   Text der Analysten. J1 rechnet über `tool nachrechnen` alle Kennzahlen zum selben Datenstand
   neu. Python vergleicht erst danach (bis 0,5 % match, bis 2 % Rundung, `config/models.yaml`).
7. **J2** sieht Aussagen unter neutraler Kennung (k-001), ohne Herkunft.
8. **Status je Claim:** `verified` nur, wenn J1 alle Referenzen bestätigt und J2 die Belegstelle
   als gedeckt sieht (supported oder partially). Nur geprüfte Claims erscheinen im Bericht.
9. **Entscheidung (HR-13):** Kategorie aus der Note. A5 kann nur senken: Liegt der Wert je Aktie
   im Base-Szenario mit A5s Stufen unter dem Kurs, wird Attraktiv zu Beobachten. Eskalationen
   (J1 mismatch bei einer Kernkennzahl, J2 contradicted, eskalierter Auftrag) setzen Eskaliert.
   Die Stufe hoch im Base-Szenario gilt nur mit geprüfter Berichtsstelle als Beleg, sonst setzt
   Python mittel.
10. **Bericht:** 14 Abschnitte aus Python-Daten über Jinja2-Vorlagen. A9 schreibt nur die These
    (höchstens drei Sätze) aus geprüften Claims. *Abweichung:* SPEC 8.3 lässt A9 den ganzen
    Überblick schreiben. Hier setzt Python die übrigen Abschnitte aus den geprüften Claims
    zusammen, damit kein ungeprüfter Text in den Bericht kommt.
11. **Dashboard:** Knopf „Tiefenanalyse starten“ startet
    `claude -p "/analyze-stock <ISIN>" --output-format stream-json --verbose --permission-mode
    dontAsk --allowedTools ...` in einer eigenen Prozesssitzung (läuft weiter, wenn der Browser
    schließt). Eine Analyse zur Zeit, weitere warten in `state/analysis_queue.yaml`.

## Abweichungen und Verschiebungen

- J1 und J2 prüfen nach der Gegenposition statt davor, damit auch Gegenposition und Erwiderung
  geprüft sind (SPEC 8.5 nennt J1, J2 vor A7).
- Erwiderung nur durch A3, eine Runde (`erwiderung_runden: 1`). SPEC 8.3 erlaubt A3 und A5 mit
  bis zu zwei Runden.
- Zeitlimit 60 statt 20 Minuten je Tiefenanalyse (`zeitlimit_minuten`): Mit Opus für A3, A5 und
  A7 sind 20 Minuten über das Abo nicht realistisch. Nach dem ersten echten Lauf anpassen.
- Noch nicht in Schritt 6: A6 Insider (Schritt 9), F1 Forensik, J3 Jury, J4 Endkontrolle,
  Mehrfachbewertung und Zwischenspeicher nach SPEC 12.5 (Schritt 10). Der Bericht nennt das.
- Gemini ist nicht angebunden. J2 läuft mit Sonnet und eigenem Prompt (Rückfall aus
  `config/models.yaml`).

## Offen, nur auf Lucas Mac prüfbar

- Läuft `claude -p` über die Anmeldung des Abos? Gelten die Hooks im Frontmatter auch im
  Hintergrundlauf? Laut Dokumentation brauchen sie einen vertrauten Projektordner.
- Fallback, wenn der Hook nicht läuft: Der Skill übergibt die Antwort selbst an
  `stockagent accept --datei`.
