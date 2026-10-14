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
| Übersicht | Kacheln mit Anzahl bewerteter Unternehmen, Notenverteilung, Eskalationen, Datenstand. Darunter die Tabelle aller Unternehmen, sortier- und filterbar nach Note, Konfidenz, Risiko, Kategorie, Branche, Land, Stufe (7.9), Größe, Datenlage und Handelbarkeitsstatus (13.5) |
| Änderungen | Was sich seit dem letzten Lauf geändert hat: neue Noten, Kategoriewechsel, neue Berichte, Restatements, Insiderkäufe, Indexauf- und -abstiege. Startseite nach jedem Lauf |
| Karte | Treemap Branche mal Land: Fläche gleich Anzahl Titel, Farbe gleich Anteil „Attraktiv“. Klick filtert die Übersicht |
| Vergleich | Zwei bis vier Unternehmen nebeneinander: Note und Säulen, Kernkennzahlen mit Trend, Bewertung, Risiken |
| Chancen-Karte | Streudiagramm Qualitätsscore (x) gegen Bewertungsscore (y), Punktgröße Marktkapitalisierung, Farbe Kategorie. Oben rechts liegen gute Firmen zu fairen Preisen |
| Unternehmensseite | Score-Zerlegung als Wasserfall, Kennzahlen-Zeitreihen mit Branchenmedian als Band, Football Field, Reverse-DCF mit implizitem Wachstum gegen Historie, Insider-Zeitachse über dem Kurs, Bear-Fall, Prüfprotokoll mit Ampel je Ebene, Belegliste mit Links |
| Eskalationen | Warteschlange mit Streitpunkten und Eingabefeld für Lucas Entscheidung (im lokalen Modus schreibt das Feld in `decisions`) |
| Historie | Alle Läufe, Notenverlauf je Titel, Notenkontrolle je Stufe gegen Index |
| Methodik | aktuelle Gewichte, Schwellen und Versionen, Änderungsprotokoll |

Gestaltung. Farben ausschließlich für Kategorien und Ampeln, nie als einziger Bedeutungsträger (zusätzlich Text oder Symbol). Hell- und Dunkelmodus. Jede Zahl mit Tooltip zur Quelle.

### 13.4 Benachrichtigung

Optional nach jedem Lauf eine kurze Nachricht mit Anzahl attraktiver Unternehmen, Eskalationen und Link zum Dashboard. Kanal konfigurierbar (E-Mail per SMTP, Telegram-Bot, Push über Claude).

### 13.5 Bedienkonzept: das Dashboard als Bedienzentrale

Ziel: Luca bedient das ganze System über das Dashboard im Browser. Er tippt nichts in Claude Code und kein Terminal. Claude Code arbeitet im Hintergrund, gestartet vom Dashboard über Lucas Abo.

**Start.** Ein Doppelklick auf `Stockagent.command` im Projektordner (macOS) oder `uv run stockagent app` startet den lokalen Server und öffnet das Dashboard im Browser. Der Server hört nur auf 127.0.0.1 (nur der eigene Rechner) und schreibt nur nach `state/` und `runs/`.

**Wie das Dashboard Claude Code nutzt.** Claude Code läuft auch ohne Bildschirm (`claude -p`, laut Dokumentation mit der Anmeldung des Abos, solange nicht `--bare` gesetzt ist). Der Server ruft es für genau zwei Dinge auf, immer mit festen Rechten und ohne Rückfragen (`--permission-prompts none`):

| Aufgabe | Aufruf | Rechte |
|---|---|---|
| Freitext in Filter übersetzen (9.9) | `claude -p` mit `--json-schema` für `request.json`, Modellklasse `fast` | keine Werkzeuge |
| Tiefenanalyse | `claude -p "/analyze-stock <ISIN>"` mit `--output-format stream-json` | nur die Werkzeuge aus 16.4 und `stockagent next | accept` |

Alles andere (Filtern, Noten, Kennzahlen, Speichern) erledigt Python ohne Modell und sofort.

**Ansicht „Suchen und Bewerten“ (Startseite).**

- Ein großes Eingabefeld: „Tier-1-Aktien aus Griechenland, Branche Automobil“. Das Dashboard zeigt darunter den verstandenen Filter als Schaltflächen (Tier 1 · Griechenland · Automobil) mit Trefferzahl. Jede Schaltfläche lässt sich wegklicken oder ändern. Bei null Treffern erscheint ein Vorschlag zum Lockern.
- Name, ISIN, WKN oder Ticker im selben Feld springen direkt zur Aktie, ohne Modellaufruf.
- Darunter die Trefferliste mit Note, Konfidenz, Risiko, Kategorie, Tier, Branche, Land, Trade-Republic-Status. Noch nicht bewertete Titel haben eine leere Notenspalte und den Knopf „Bewerten“: Er holt Kurse und Kennzahlen des Titels und seiner Vergleichsgruppe (15 bis 50 Titel) und rechnet die Note ohne Sprachmodell, in Sekunden bis wenigen Minuten (ADR 0005). Knöpfe „Alle bewerten“ und „Auswahl bewerten“ starten die Tiefenanalyse für die besten Treffer bis zur Grenze aus HR-18. Vorher zeigt das Dashboard den Laufplan (Anzahl, geschätzte Dauer, Hinweis auf das Kontingent des Abos) und wartet auf Bestätigung.

**Filterleiste** in der Übersicht, jeder Filter mit Anzahl Treffer je Wert:

- Stufe: Tier 1 bis 4 (7.9)
- Land und Region: Hauptsitz, wahlweise Rechtssitz. Regionen als Gruppen (DACH, Europa, Nordamerika, Asien-Pazifik, Schwellenländer)
- Branche: Hauptbranche, aufklappbar bis Unterbranche (`config/sectors.yaml`)
- Größenklasse (3.1), Note, Konfidenz, Risiko, Kategorie (6.5)
- Handelbarkeit bei Trade Republic: bestätigt, nicht handelbar, ungeprüft
- Datenlage: Abschlussdaten aus SEC, ESEF, Anbieter oder keine (erklärt jedes N)
- Nur Beobachtungsliste

Filter stehen in der Adresszeile, eine Ansicht lässt sich als Lesezeichen speichern oder mit Namen ablegen („Tier 1 Europa Qualität“, `state/views.yaml`).

**Klick auf eine Aktie** öffnet ihre Seite. Ohne Tiefenanalyse zeigt sie Note, Säulenzerlegung, Kennzahlen mit Rechenweg und Datenqualität sofort. Der Knopf „Tiefenanalyse starten“ startet Claude Code im Hintergrund. Die Seite zeigt den Fortschritt je Abteilung (Recherche, Berechnung, Auswertung, Prüfung, mit dem gerade arbeitenden Agenten) und danach den finanziellen Überblick mit 14 Abschnitten. Läuft schon eine Analyse, kommt die neue in die Warteschlange `state/analysis_queue.yaml`. Schließen des Browsers bricht nichts ab, der Zustandsautomat setzt fort (8.6).

**Weitere Bedienelemente:**

- Stern für die Beobachtungsliste (`state/watchlist.yaml`) und ein Notizfeld je Titel (`state/notes.yaml`), ohne Einfluss auf die Note.
- Trade-Republic-Prüfung direkt in der Zeile (ja oder nein, schreibt `state/tr_checks.yaml`).
- Knopf „Daten aktualisieren“ für Universum und SEC-Daten mit Fortschrittsanzeige (Python, kein Modell).
- Eskalationen mit beiden Werten, Quellen und Eingabefeld für Lucas Entscheidung.
- Spaltenwahl und Export der gefilterten Liste als CSV.
- Jede Zahl mit Tooltip zu Quelle und Rechenweg (13.1), jede Note mit Zerlegung, jedes N mit Grund.
- Abdeckungsanzeige oben, etwa „14.509 Aktien, davon 3.117 mit Note, Rest ohne strukturierte Daten (Grund je Titel)“ (HR-16).
- Anzeige des Abo-Verbrauchs der letzten Läufe aus `log.jsonl`, damit Luca vor großen Läufen sieht, was sie kosten.
- Hell- und Dunkelmodus, lesbar auf dem Handy (Tabelle wird zu Karten).

**Lesemodus.** Dieselbe Seite lässt sich als statische Datei (13.3) oder als privates Artifact teilen. Dort gehen Ansehen, Filtern und Suchen nach Name. Freitext, Bewerten und Speichern brauchen den lokalen Server und sind dann ausgeblendet.

Claude Code im Terminal (`/stockagent`, `/analyze-stock`) bleibt als zweiter Weg erhalten, etwa für Rückfragen zu einem Bericht. Nötig ist er nicht.
