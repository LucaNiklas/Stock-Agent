## 19. Offene Entscheidungen für Luca

| Nr. | Frage | Default im Code | Nötig ab |
|---|---|---|---|
| 1 | Kommerzieller Datenanbieter für Kurse, zweite Quelle und Märkte ohne XBRL? | entschieden 14.10.2026 für die Kurse: Yahoo, kein bezahlter Anbieter (ADR 0005). Offen für Abschlusszahlen außerhalb USA und EU: Titel ohne strukturierte Daten erhalten Status N | Schritt 7 |
| 2 | Höchstzahl Tiefenanalysen je Lauf (Abo-Limits schonen) | 3 | Schritt 6 |
| 3 | Gemini über Lucas Google-Konto als externer Prüfer (8.8)? Falls die Anmeldung mit AI Plus nicht funktioniert: Gemini-API-Schlüssel mit Abrechnung oder nur Claude? | Gemini über Google-Konto versuchen, sonst nur Claude | Schritt 10 |
| 4 | Zeitplan und API-Betrieb (kostet pro Token) für Läufe ohne Luca? | nein, Start von Hand über das Abo | Schritt 12 |
| 5 | Eskalationen auch als GitHub-Issues? | ja | Schritt 10 |
| 6 | Markierungen nach eigenen Werten (Branchen, Länder), ohne Einfluss auf die Note | keine | jederzeit |
| 7 | Sollen die zurückgestellten Module aus Anhang A später gebaut werden? | nein | jederzeit |
| 8 | Teilen (18.6): Lizenz, und läuft die Plattform bei jedem Nutzer selbst oder zentral? | jeder installiert sie bei sich | Baustein F |
| 9 | Autonomer Betrieb (18.6): welches Sprachmodell ersetzt Claude (andere API, lokales Modell)? | offen, Entscheidung nach Goldstandard-Vergleich | Baustein G |

Kostenlose Kursdaten in Dauerqualität sind knapp. `yfinance` ist inoffiziell und nur für die Entwicklung zugelassen. Spätestens in Schritt 4 klärt Claude Code mit Luca, ob eine offizielle kostenlose Quelle reicht oder Entscheidung 1 nötig wird.
