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

### 13.5 Bedienkonzept

Ziel: Luca findet jede Aktie des Universums über Filter oder Freitext, sieht ihre Note sofort und startet die Tiefenanalyse mit einem Klick.

**Zwei Betriebsarten.**

| Art | Technik | Kann |
|---|---|---|
| Lesen | statische HTML-Datei (13.3), auch als privates Artifact | ansehen, filtern, sortieren, suchen, vergleichen |
| Arbeiten | lokaler Server `stockagent serve` auf 127.0.0.1, dieselbe Seite plus kleine Schnittstelle | zusätzlich Beobachtungsliste, Trade-Republic-Prüfung und Notizen speichern, Tiefenanalyse anfordern |

Eine statische Seite kann nichts speichern und nichts starten. Deshalb gibt es den lokalen Server. Er hört nur auf dem eigenen Rechner (127.0.0.1) und schreibt nur nach `state/`.

**Filterleiste** über der Tabelle, jeder Filter mit Anzahl Treffer je Wert:

- Stufe: Tier 1 bis 4 (7.9)
- Land und Region: Hauptsitz, wahlweise Rechtssitz. Regionen als Gruppen (DACH, Europa, Nordamerika, Asien-Pazifik, Schwellenländer)
- Branche: Hauptbranche, aufklappbar bis Unterbranche (`config/sectors.yaml`)
- Größenklasse (3.1), Note, Konfidenz, Risiko, Kategorie (6.5)
- Handelbarkeit bei Trade Republic: bestätigt, nicht handelbar, ungeprüft
- Datenlage: Abschlussdaten aus SEC, ESEF, Anbieter oder keine (erklärt jedes N)
- Nur Beobachtungsliste

Filter stehen in der Adresszeile der Seite, eine Ansicht lässt sich also als Lesezeichen speichern.

**Suchfeld** mit zwei Bedeutungen: Name, ISIN, WKN oder Ticker springt direkt zum Titel. Ein Satz („Tier 1 Griechenland Automobil“) wird nach 9.9 in Filter übersetzt und als Filterleiste angezeigt. Im Lesemodus übersetzt eine feste Wortliste (Länder, Branchen, Stufen, Noten), Freitext mit Sprachmodell nur im Arbeitsmodus über Claude Code.

**Klick auf eine Aktie** öffnet ihre Seite (Unternehmensseite aus 13.3). Ohne Tiefenanalyse zeigt sie Note, Säulenzerlegung, Kennzahlen mit Rechenweg und Datenqualität sofort, weil alles schon berechnet ist. Der Knopf „Tiefenanalyse“ (nur Arbeitsmodus):

1. schreibt die ISIN in die Warteschlange `state/analysis_queue.yaml`,
2. startet, wenn Luca es in `config/run_profiles.yaml` erlaubt, Claude Code ohne Bildschirm (`claude -p "/analyze-stock <ISIN>"`) über Lucas Abo, sonst arbeitet `/stockagent` die Warteschlange beim nächsten Start ab,
3. zeigt den Fortschritt aus `runs/<run_id>/` (welche Abteilung arbeitet gerade) und danach den finanziellen Überblick.

Mehrfachauswahl in der Tabelle legt mehrere Titel gleichzeitig in die Warteschlange. Die Grenze aus HR-18 gilt auch hier.

**Weitere Bedienelemente:**

- Stern für die Beobachtungsliste (`state/watchlist.yaml`) und ein Notizfeld je Titel (`state/notes.yaml`), beides nur Lucas Eingaben, ohne Einfluss auf die Note.
- Trade-Republic-Prüfung direkt in der Zeile (ja oder nein, schreibt `state/tr_checks.yaml` wie `stockagent tr-check`).
- Spaltenwahl und Export der gefilterten Liste als CSV.
- Jede Zahl mit Tooltip zu Quelle und Rechenweg (13.1), jede Note mit Zerlegung, jedes N mit Grund.
- Abdeckungsanzeige oben, etwa „14.509 Aktien, davon 3.117 mit Note, Rest ohne strukturierte Daten (Grund je Titel)“, damit sichtbar bleibt, was noch fehlt (HR-16).
- Hell- und Dunkelmodus, lesbar auf dem Handy (Tabelle wird zu Karten).
