## 13. Nachvollziehbarkeit und Darstellung

### 13.1 Audit-Trail

- Jede Zahl im Bericht ist anklickbar und führt zu Kennzahl-ID, Formel, Eingabewerten und deren Quelle (XBRL-Konzept oder PDF-Seite mit Zitat).
- Jeder Lauf ist reproduzierbar. Das Manifest enthält Git-Commit, Hashes aller Konfigurationsdateien, Modellnamen und -versionen, Prompt-Hashes und den Datenstand (höchstes `published_at`).
- Rohdokumente werden nie gelöscht oder überschrieben.
- `log.jsonl` protokolliert jede Modellanfrage und jeden Werkzeugaufruf mit Tokens und Kosten.

### 13.2 Laufübersicht (Bericht je Lauf)

Aufbau der Laufübersicht `report.md` und `report.html`. Jede verlinkte Einzelanalyse folgt der Gliederung aus 12.3.

1. Kopf. Datum, Lauf-ID, Datenstand, Methodik-Version, Hinweis "Recherche-Grundlage, keine Anlageberatung".
2. Kurzfassung in fünf Sätzen. Was hat sich seit dem letzten Lauf geändert?
3. Rangliste der angefragten Kategorie (Tabelle). Name, ISIN, Handelbarkeitsstatus bei Trade Republic, Branche, Land, Note · Konfidenz · Risiko, Kategorie, Bewertungsbedingung aus 3.6, implizites Wachstum, Insider-Signal.
4. Je tiefenanalysiertem Unternehmen eine Seite. These in drei Sätzen, Kennzahlen-Übersicht mit Trend, Bewertungsdiagramm (Football Field), Bear-Fall mit Beobachtungsindikatoren, Prüfstatus aller Ebenen, Belegliste, Link zum vollständigen Überblick.
5. Beobachtungsliste mit Veränderungen seit dem letzten Lauf.
6. Eskalierte Fälle mit Streitpunkten.
7. Notenkontrolle (Abschnitt 14).
8. Methodische Hinweise, Grenzen dieses Laufs und Änderungen seit dem letzten Lauf.

### 13.3 Dashboard

Das Dashboard ist eine statische Webseite, die aus den Laufdaten gebaut wird. Damit läuft es überall und braucht keinen Server.

- Technik. Das Modul `dashboard/build.py` schreibt eine einzelne HTML-Datei mit eingebetteten Daten (JSON) und Diagrammen in Plotly.js oder ECharts. Alternative für lokale Nutzung mit Interaktion ist Streamlit. Die statische Variante ist Default, weil sie als Artifact in Claude veröffentlicht oder einfach als Datei geöffnet werden kann.
- Veröffentlichung. Optional als privates Artifact in Claude, das bei jedem Lauf aktualisiert wird.

Ansichten.

| Ansicht | Inhalt |
|---|---|
| Übersicht | Kacheln mit Anzahl bewerteter Unternehmen, Notenverteilung, Eskalationen, Datenstand. Darunter die Tabelle aller Unternehmen, sortier- und filterbar nach Note, Konfidenz, Risiko, Branche, Land, Größe und Handelbarkeitsstatus |
| Chancen-Karte | Streudiagramm Qualitätsscore (x) gegen Bewertungsscore (y), Punktgröße Marktkapitalisierung, Farbe Kategorie. Oben rechts liegen gute Firmen zu fairen Preisen |
| Unternehmensseite | Score-Zerlegung als Wasserfall, Kennzahlen-Zeitreihen mit Branchenmedian als Band, Football Field, Reverse-DCF mit implizitem Wachstum gegen Historie, Insider-Zeitachse über dem Kurs, Bear-Fall, Prüfprotokoll mit Ampel je Ebene, Belegliste mit Links |
| Eskalationen | Warteschlange mit Streitpunkten und Eingabefeld für Lucas Entscheidung (im lokalen Modus schreibt das Feld in `decisions`) |
| Historie | Alle Läufe, Notenverlauf je Titel, Notenkontrolle je Stufe gegen Index |
| Methodik | aktuelle Gewichte, Schwellen und Versionen, Änderungsprotokoll |

Gestaltung. Farben ausschließlich für Kategorien und Ampeln, nie als einziger Bedeutungsträger (zusätzlich Text oder Symbol). Hell- und Dunkelmodus. Jede Zahl mit Tooltip zur Quelle.

### 13.4 Benachrichtigung

Optional nach jedem Lauf eine kurze Nachricht mit Anzahl attraktiver Unternehmen, Eskalationen und Link zum Dashboard. Kanal konfigurierbar (E-Mail per SMTP, Telegram-Bot, Push über Claude).
