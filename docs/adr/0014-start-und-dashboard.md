# ADR 0014: Start und Dashboard, Suche in eigenen Worten, Laufplan (Bauschritt 11)

Status: angenommen (22.10.2026, Lucas Vorgabe „selbst entscheiden, ADR“ für Bauschritt 11).

## Kontext

SPEC 9.6, 9.7, 9.9, 13.3 und 13.5 verlangen: alle Startwege (Dashboard, `/stockagent`,
`stockagent run` mit Dialog oder Optionen), eine Suche in ganzen Sätzen, die nichts rät, einen
Laufplan vor jedem Lauf mit Tiefenanalyse und die Ansichten Änderungen, Karte, Vergleich,
Historie und Methodik. Abnahme laut BAUPLAN: alle Startwege schreiben `request.json`, zehn
Beispielsätze werden richtig übersetzt, ein Satz mit unbekanntem Land oder unbekannter Branche
wird abgelehnt.

## Entscheidung

1. **Eine Anfrage, ein Schema.** `anfrage.Anfrage` (Pydantic, `extra = forbid`) ist der Inhalt
   von `request.json`, `state/last_request.yaml`, der Profile und gespeicherten Ansichten. Felder:
   Stufen, Länder, Region, Haupt- und Unterbranchen (IDs aus `config/sectors.yaml`), Größen,
   Noten, Kategorien, Stile, Horizont, Handelbarkeit, Beobachtungsliste, Tiefe, Suche, ISINs. Jeder
   Weg (Wortliste, Modell, Dialog, Optionen, Profil, Ansicht, Dashboard) endet in diesem Modell
   und läuft durch `anfrage.pruefen`: ein Wert außerhalb der Listen lehnt ab.
2. **Wortliste zuerst** (`config/vokabular.yaml`): Länder mit deutschen und englischen Namen und
   Adjektiven („europäische“, „deutsche“), Regionen (zusätzlich DACH), Branchenwörter auf die IDs
   aus `config/sectors.yaml`, Größen, Kategorien, Stile, Horizonte, Tiefe. „Tier 1 bis 2“ und
   „Note A oder B“ über Muster. Folgt auf „aus“, „in“, „Land“, „Branche“, „Sektor“ oder „Bereich“
   ein unbekanntes Wort, lehnt die Wortliste ab, ohne das Modell zu fragen. Erkennt sie nichts,
   ist der Text ein Name, eine ISIN oder WKN und springt ohne Modell zur Aktie.
3. **Modell nur für Reste** (`claude -p --json-schema`, Modellklasse `fast` über
   `U0_uebersetzer` in `config/models.yaml`, `--tools ""`, Vorlage
   `agents/prompts/uebersetzer.md` 1.0.0). Das Schema erlaubt je Feld nur die Listenwerte als
   Aufzählung und ein Feld `unbekannt`. Lucas Satz steht zwischen Markierungen als Daten
   (HR-17). Was das Modell unter `unbekannt` meldet, ein Thema ohne Branchencode oder ein Wert
   außerhalb der Listen, lehnt ab. Ist Claude Code nicht da oder scheitert der Aufruf, gilt das
   Ergebnis der Wortliste und die nicht verstandenen Wörter stehen als Hinweis daneben.
4. **Laufplan vor jedem Lauf** (`lauf.planen`): Auswahl, aktuelle Noten, Titel zum Bewerten,
   Titel ohne Daten, Tiefenanalysen und geschätzte Dauer (`core/laufplan.py` über den Rechenweg,
   Schätzwerte in `config/run_profiles.yaml`). Gestartet wird erst nach Bestätigung: im Dashboard
   über einen Knopf, der nur einen gezeigten Plan einmal ausführt, im Terminal über eine Rückfrage
   oder `--yes`.
5. **Grenzen.** Tiefe „Standard“ sieht 10, „Tief“ 25 Tiefenanalysen vor (SPEC 9.7), die harte
   Grenze je Lauf bleibt 3 (HR-18, `max_tiefenanalysen_je_lauf`). Der Plan nennt beide Zahlen.
   Neu ist eine Grenze von 250 Bewertungen je Lauf, damit „Alle bewerten“ über das ganze
   Universum nicht stundenlang läuft. Note, Kategorie, Stil und Größe stehen erst nach dem
   Bewerten fest: bewertet wird die Auswahl nach den übrigen Filtern, die Rangliste filtert danach.
   Eine Note gilt nach `vergleichsgruppe.erneuern_tage` (7 Tage) als veraltet und wird neu
   gerechnet.
6. **Auswahl der Tiefenanalysen** (`lauf.auswahl_tief`): Note, dann Konfidenz, dann Gesamtwert,
   nur K1 bis K3. Titel der Beobachtungsliste zuerst, wenn Luca das wählt, innerhalb derselben
   Grenze. Im Dashboard laufen sie über die bestehende Warteschlange, im Terminal nacheinander,
   im Skill `/stockagent` über `/analyze-stock` in derselben Sitzung (`--tiefenanalyse liste`).
7. **Anlagestile als Filter** auf schon berechnete Werte (`config/run_profiles.yaml`): Qualität,
   Günstige Bewertung und Wachstum über die Säule (Perzentil mindestens 70), Dividende über die
   Dividendenrendite (mindestens 3 %), Insider-Käufe über das Signal. Kein Einfluss auf die Note.
   „Turnaround“ hat kein deterministisches Merkmal und wird abgelehnt, bis Luca eines festlegt.
8. **Ablage.** Läufe unter `runs/_laeufe/<lauf_id>/` (`request.json`, `plan.json`,
   `ergebnis.json`, `report.md` als Laufübersicht nach SPEC 13.2 Teile 1 bis 3, 6 und 8). Die
   Tiefenanalysen behalten ihre Läufe unter `runs/<run_id>/`. Gespeicherte Ansichten in
   `state/views.yaml`, eine Ansicht lässt sich im Suchfeld mit ihrem Namen aufrufen.
9. **Ansichten im Dashboard** als Reiter derselben Seite: Änderungen (Noten- und
   Kategoriewechsel aus `grade_snapshots`, neue Berichte, Restatements über `superseded_by`,
   Insiderkäufe, Indexauf- und -abstiege seit dem vorletzten Tagesstand), Karte, Vergleich (2 bis
   4 angekreuzte Titel), Historie (Läufe, Tiefenanalysen, Stand der Notenkontrolle), Methodik
   (Gewichte, Schwellen, Versionen, Änderungsprotokoll). Notenverlauf auf der Unternehmensseite.
10. **Claude Code finden.** `claude_cli.pfad` sucht `claude` im PATH und an den üblichen Orten
    (`~/.claude/local`, `~/.local/bin`, Homebrew), weil der Doppelklick-Start die Shell-Einstellungen
    nicht liest. Das Dashboard zeigt einen Hinweis, wenn Claude Code fehlt.

## Abweichungen von der Spezifikation

- **Karte:** statt einer Treemap mit Bibliothek eine Kachelkarte in reinem HTML (Zeilen je
  Branche, Fläche nach Anzahl, Länder unter 4 % einer Zeile als „übrige“). Grund: keine externe
  Bibliothek, funktioniert ohne Netz und im Dunkelmodus. Die Farbe zeigt den Anteil Attraktiv
  unter den bewerteten Titeln, schraffiert heißt noch nicht bewertet, der Anteil steht zusätzlich
  als Zahl in der Kachel.
- **Chancen-Karte** (Streudiagramm Qualität gegen Bewertung) ist nicht gebaut, der Vergleich
  zeigt dieselben Säulen nebeneinander.
- **Themen ohne Branchencode** (Agent A0, Suche in den Geschäftsbeschreibungen) sind nicht
  gebaut. Solche Anfragen werden mit diesem Grund abgelehnt.
- **Abo-Verbrauch aus `log.jsonl`** wird noch nicht angezeigt. Der Laufplan nennt den Hinweis auf
  das Kontingent aus `config/run_profiles.yaml`.
- **`--budget-eur`** wird angenommen und im Plan vermerkt, wirkt aber erst im API-Betrieb
  (Bauschritt 12).
- **Neuanalyse statt Wiederholung (SPEC 9.4)** ist nicht gebaut: eine Tiefenanalyse läuft immer
  neu.

## Nebenbei behoben

- Norwegen stand in vier Konfigurationsdateien als `NO` ohne Anführungszeichen, YAML liest das als
  „falsch“. Folgen: keine Region in der Vergleichsgruppe, kein Steuersatz, kein Kurskürzel `.OL`.
  Korrigiert, Test für alle Konfigurationsdateien, Methodik 5.7.
- Die Liste aller Titel liegt jetzt in `titelliste.py`, damit Dashboard und `stockagent run`
  dieselbe Filterlogik nutzen. Filter nehmen mehrere Werte mit Komma an.
- Neue Abfragen auf `facts` stehen in `store.py` (HR-07-Test), die Datenlage unterscheidet SEC,
  ESEF und keine Daten.

## Fragen an Luca

1. Woran soll „Turnaround“ als Stil erkannt werden (etwa Note D oder E vor einem Jahr, heute C
   mit steigender Marge)? Bis dahin abgelehnt.
2. Sind 250 Bewertungen je Lauf und 3 Tiefenanalysen je Lauf die richtigen Grenzen?
