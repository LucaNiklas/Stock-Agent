## 9. Ablauf eines Laufs

### 9.1 Rhythmus

- Normalfall ist der Start auf Anfrage (9.7).
- Optional ein Zeitplan (`config/run_profiles.yaml`, Profil `scheduled`), Default aus. Ein täglicher Leichtlauf (nur Python, keine Modellkosten) kann Ereignisse prüfen und Beobachtungstitel markieren.

### 9.2 Ereignisauslöser für Einzelanalysen

Nur wenn der Zeitplan aktiv ist.

| Ereignis | Bedingung |
|---|---|
| Neuer Bericht | neuer Jahres- oder Halbjahresbericht bei einem Titel der Beobachtungsliste |
| Insider-Cluster | Cluster nach 3.8 Punkt 5 bei einem Titel im Universum |
| Warnsignal | neue Ad-hoc-Mitteilung zu Prognosesenkung, Prüferwechsel, Restatement bei einem Titel der Beobachtungsliste |

### 9.3 Laufschritte

1. Konfiguration laden, Hashes ins Manifest.
2. Universum aktualisieren (wöchentlich) oder aus Cache.
3. Daten nachladen (inkrementell, nur neue Einreichungen).
4. P2 bis P6 deterministisch für alle Unternehmen.
5. Liste der Tiefenanalysen aus der Anfrage (9.8) und der Beobachtungsliste bilden.
6. Tiefenanalyse (8.5).
7. Bericht und Endkontrolle.
8. Dashboard bauen, optional Benachrichtigung.
9. Notenkontrolle fortschreiben (Abschnitt 14).

### 9.4 Neuanalyse statt Wiederholung

Hat sich bei einem Titel seit der letzten Tiefenanalyse weder ein Bericht noch ein Insidergeschäft noch der Kurs um mehr als 10 Prozent verändert, übernimmt das System die vorige Tiefenanalyse und rechnet nur die Bewertung neu. Das spart den Großteil der Kosten.

### 9.5 Hysterese gegen Hin-und-Her

- Ein Unternehmen wird erst "Attraktiv", wenn es Note A oder B in zwei aufeinanderfolgenden Läufen erreicht oder eine Tiefenanalyse es bestätigt.
- Zwischen Note B und Note D liegt bewusst die neutrale Note C als Puffer.

### 9.6 Den Agenten starten

Grundsatz. Die quantitative Note (Abschnitt 6) wird bei jedem Lauf für alle Unternehmen berechnet. Das kostet keine Modellaufrufe. Die gewählte Kategorie bestimmt nur, welche Unternehmen zusätzlich eine Tiefenanalyse mit Agenten bekommen.

| Weg | Befehl | Wann |
|---|---|---|
| In Claude Code | im Repository `claude` starten, dann `/stockagent` | Normalfall. Der Skill fragt die Kategorie ab (9.7), zeigt den Laufplan und startet nach Bestätigung |
| Im Terminal ohne Claude Code | `uv run stockagent run` | Dieselben Fragen als Terminal-Dialog (Bibliothek `questionary`) |
| Ohne Rückfragen | `uv run stockagent run --category sector:health_care --region europe --size small,mid --depth standard --budget-eur 10 --yes` | Skripte und Wiederholungen |
| Nur Noten | `uv run stockagent screen` | Aktualisiert Universum und Noten ohne Tiefenanalyse |
| Einzeltitel | `/analyze-stock <ISIN oder Name>` oder `uv run stockagent analyze <ISIN>` | Finanzieller Überblick über ein Unternehmen |
| Status und Ergebnisse | `uv run stockagent status`, `uv run stockagent dashboard --open` | Letzte Läufe, offene Eskalationen |

Vor jedem Lauf mit Tiefenanalyse zeigt das System einen Laufplan mit Datenstand, Anzahl geplanter Tiefenanalysen, geschätzten Modellkosten und Dauer. Ohne `--yes` startet der Lauf erst nach Bestätigung.

### 9.7 Kategorie-Abfrage

In Claude Code nutzt der Skill `/stockagent` das Werkzeug AskUserQuestion (bis zu vier Fragen mit je zwei bis vier Optionen, Mehrfachauswahl, immer ein Freitextfeld). Der Dialog läuft deshalb in zwei Runden. Im Terminal stellt `questionary` dieselben Fragen.

**Runde 1**

| Frage | Optionen | Mehrfachauswahl |
|---|---|---|
| Was soll ich bewerten? | Branche, Region oder Land, Anlagestil, Gesamtmarkt (beste Noten). Freitext für Thema oder Einzeltitel | nein |
| Welche Größenklassen? | Large und Mega, Mid, Small, Micro und Nano | ja |
| Wie tief? | Schnell (nur Noten, keine Tiefenanalyse), Standard (Tiefenanalyse der besten 10), Tief (beste 25) | nein |
| Handelbarkeit bei Trade Republic? | Alle (empfohlen), nur von Luca als handelbar geprüfte | nein |

**Runde 2 (abhängig von Runde 1)**

| Auswahl | Rückfrage |
|---|---|
| Branche | Der Skill zeigt die nummerierte Liste der Branchen (`config/sectors.yaml` mit 11 Hauptbranchen und Unterbranchen) als Text und nimmt die Auswahl über das Freitextfeld an, etwa "2, 5" |
| Region oder Land | Deutschland, Europa, Nordamerika, Asien-Pazifik und Schwellenländer. Einzelne Länder über Freitext |
| Anlagestil | Qualität, günstige Bewertung, Wachstum, Dividende. Freitext für "Insider-Käufe" oder "Turnaround" |
| Thema (Freitext, etwa "Halbleiter" oder "Wasser") | Der Kategorie-Agent A0 sucht passende Unternehmen ausschließlich in den gespeicherten Geschäftsbeschreibungen und Branchencodes, nie aus Vorwissen (HR-04). Er zeigt die Trefferliste mit Belegstelle je Unternehmen. Luca bestätigt oder streicht, bevor Tiefenanalysen starten |
| Einzeltitel | Auflösung von Name oder Ticker auf ISIN und LEI. Bei mehreren Treffern Auswahlfrage |

Die Antworten werden in `runs/<run_id>/request.json` gespeichert und als Vorschlag für den nächsten Start in `state/last_request.yaml` abgelegt.

Innerhalb der Kategorie sortiert das System nach Note, dann nach Konfidenz. Tiefenanalysen bekommen die besten Unternehmen mit Konfidenz K1 bis K3. Zusätzlich geht die Beobachtungsliste (`state/watchlist.yaml`) in die Tiefenanalyse, wenn Luca das wählt.

### 9.8 Rückfragen während und nach dem Lauf

Der Agent fragt Luca nur an festen Stellen. Beim Start fragt er nach der Kategorie. Bei einem Themen-Lauf bestätigt Luca die Trefferliste. Nach dem Lauf werden eskalierte Fälle vorgelegt (`/review-escalations` in Claude Code oder GitHub-Issues, Abschnitt 16.14). In Läufen nach Zeitplan stellt er keine Fragen. Was eine Entscheidung braucht, landet in der Eskalations-Warteschlange.
