## 19. Offene Entscheidungen für Luca

| Nr. | Frage | Default im Code | Nötig ab |
|---|---|---|---|
| 1 | Kommerzieller Datenanbieter für Kurse, zweite Quelle und Märkte ohne XBRL? | keiner, nur kostenlose Quellen. Titel ohne strukturierte Daten erhalten Status N | Schritt 4 (Kurse) |
| 2 | Monatliches Budget für Modellkosten | 20 EUR, `max_cost_per_run_eur` 10 | Schritt 6 |
| 3 | Welche Modellanbieter stehen für die Jury zur Verfügung? | nur Claude mit Hinweis im Bericht | Schritt 10 |
| 4 | Ausführungsort für spätere Zeitpläne (lokal, Routine, GitHub Actions) | lokal, Zeitplan aus | Schritt 12 |
| 5 | Eskalationen auch als GitHub-Issues? | ja | Schritt 10 |
| 6 | Markierungen nach eigenen Werten (Branchen, Länder), ohne Einfluss auf die Note | keine | jederzeit |
| 7 | Sollen die zurückgestellten Module aus Anhang A später gebaut werden? | nein | jederzeit |

Kostenlose Kursdaten in Dauerqualität sind knapp. `yfinance` ist inoffiziell und nur für die Entwicklung zugelassen. Spätestens in Schritt 4 klärt Claude Code mit Luca, ob eine offizielle kostenlose Quelle reicht oder Entscheidung 1 nötig wird.
