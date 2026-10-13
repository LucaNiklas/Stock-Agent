# ADR 0004: Bedienkonzept und Indexstufe

Status: vorgeschlagen (13.10.2026), angenommen mit Lucas Merge des Pull Requests

## Kontext

Luca will Aktien nach Branche, Land und einer Stufe filtern, die sagt, wie etabliert eine Aktie ist („Tier 1 = in den großen Indizes“). Er will entweder in eigenen Worten suchen („Tier-1-Aktien aus Griechenland, Branche Automobil, bewerte sie“) oder in der Liste eine Aktie anklicken und bewerten lassen.

Randbedingungen:

- Die Note entsteht nur aus deterministischen Werten (HR-13). Eine Stufe darf sie nicht verändern.
- Agenten laufen über Lucas Claude-Abo in Claude Code (SPEC 15.1), nicht über einen API-Schlüssel. Eine Webseite kann sie nicht direkt starten.
- Eine statische HTML-Seite kann nichts speichern.
- Indexzusammensetzungen sind oft lizenzpflichtig. Frei verfügbar sind Positionsdateien von ETFs und manche Veröffentlichungen von Börsen.

## Entscheidung

1. **Indexstufe Tier 1 bis 4** (SPEC 7.9), bezogen auf den Heimatmarkt: Leitindex, breiter Standardindex, Nebenwerte-Index, ohne Index. Höchste zutreffende Stufe zählt. Reiner Filter, ohne Einfluss auf die Note. Absolute Größe bleibt die Größenklasse aus SPEC 3.1.
   - Verworfen: „Tier 1 nur, wer in mehreren globalen Indizes steht“. Damit gäbe es in Griechenland, Österreich oder Portugal fast nie Tier 1, Lucas Beispiel liefe ins Leere.
   - Verworfen: Stufe aus Marktkapitalisierung. Das wäre eine zweite Größenklasse und sagt nichts über Bekanntheit und Abdeckung.
2. **Das Dashboard ist die Bedienzentrale** (SPEC 13.5, Lucas Wunsch 13.10.2026): Luca tippt nichts in Claude Code. Ein lokaler Server auf 127.0.0.1 (`stockagent app`, Doppelklick-Start) zeigt das Dashboard und startet Claude Code im Hintergrund ohne Bildschirm (`claude -p`). Laut Dokumentation nutzt `claude -p` die Anmeldung des Abos, solange nicht `--bare` gesetzt ist, führt Skills aus und liefert mit `--json-schema` Antworten in festem Format. Eine statische Kopie zum Ansehen (auch als Artifact) bleibt möglich.
3. **Freitext wird zu Filtern** (SPEC 9.9): Eine feste Wortliste versteht einfache Sätze ohne Modell. Sonst übersetzt ein Aufruf von Claude Code ohne Werkzeuge den Satz in `request.json` mit erlaubten Werten, zeigt den verstandenen Filter und die Trefferzahl und wartet auf Bestätigung. Die Treffer kommen aus der Datenbank, nie aus dem Vorwissen eines Modells.
4. **Bewerten per Klick**: Note, Konfidenz und Risiko sind für alle Titel vorab berechnet und erscheinen sofort. Der Knopf „Tiefenanalyse starten“ startet `claude -p "/analyze-stock <ISIN>"` mit festen Rechten. Läuft schon eine Analyse, wartet die neue in einer Warteschlange. Ab Schritt 6.

## Folgen

- Schritt 5 bekommt die Indexstufe und das Dashboard als Bedienzentrale mit Suchfeld und Filterleiste. Schritt 6 den Start der Tiefenanalyse per Klick. Schritt 10 die Eskalationen im Dashboard. Schritt 11 die Suche in ganzen Sätzen, „Alle bewerten“, gespeicherte Ansichten und weitere Ansichten (Änderungen, Karte, Vergleich).
- Vor Schritt 6 wird auf Lucas Mac geprüft, dass `claude -p` über das Abo läuft. Sonst bleibt die Warteschlange, die Claude Code beim nächsten Start abarbeitet.
- Korrektur in ADR 0003: Subagents können verschachtelt werden. Die Leitung bleibt beim Zustandsautomaten. Übersicht im BAUPLAN unter „Fahrplan Oberfläche“.
- Für jeden Index muss in Schritt 5 eine freie Quelle mit ISIN gefunden und geprüft werden. Fehlt sie für ein Land, hat dieses Land vorerst kein Tier 1, und die Übersicht sagt das.
