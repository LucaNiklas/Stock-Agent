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
2. **Zwei Betriebsarten** (SPEC 13.5): Lesemodus als statische Seite (auch als Artifact) und Arbeitsmodus über einen lokalen Server auf 127.0.0.1, der nur nach `state/` schreibt.
3. **Freitext wird zu Filtern** (SPEC 9.9): Die Hauptsitzung übersetzt den Satz in `request.json` mit erlaubten Werten, zeigt den verstandenen Filter und die Trefferzahl und wartet auf Bestätigung. Die Treffer kommen aus der Datenbank, nie aus dem Vorwissen eines Modells.
4. **Bewerten per Klick**: Note, Konfidenz und Risiko sind für alle Titel vorab berechnet und erscheinen sofort. Die Tiefenanalyse geht über eine Warteschlange, die Claude Code abarbeitet. Ein Start direkt aus dem Browser über `claude -p` kommt in Schritt 11, nur wenn Luca es erlaubt und die Dokumentation bestätigt, dass es über das Abo läuft.

## Folgen

- Schritt 5 bekommt die Indexstufe, die Filterleiste, das Suchfeld und den Arbeitsmodus. Schritt 6 den Klick auf „Tiefenanalyse“. Schritt 11 die Freitext-Abfrage, gespeicherte Ansichten und weitere Ansichten (Änderungen, Karte, Vergleich). Übersicht im BAUPLAN unter „Fahrplan Oberfläche“.
- Für jeden Index muss in Schritt 5 eine freie Quelle mit ISIN gefunden und geprüft werden. Fehlt sie für ein Land, hat dieses Land vorerst kein Tier 1, und die Übersicht sagt das.
