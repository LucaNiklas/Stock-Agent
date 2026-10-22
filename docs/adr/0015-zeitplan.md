# ADR 0015: Lauf nach Zeitplan über das Abo, ohne API-Schlüssel (Bauschritt 12)

Status: angenommen (22.10.2026, Lucas Auftrag „baue jetzt noch die letzten Bauschritte“, Vorgabe
„selbst entscheiden, ADR“).

## Kontext

Bauschritt 12 ist optional: Läufe ohne Luca, etwa täglich oder wöchentlich (SPEC 9.1, 9.2, 15.2,
16.14). Offen war die Entscheidung SPEC 19 Nr. 4, ob dafür ein API-Schlüssel mit Kosten pro Token
genutzt wird. Default der Spezifikation: nein, Start von Hand über das Abo.

## Entscheidung

1. **Kein API-Betrieb.** Der Zeitplan läuft lokal auf Lucas Mac. Der tägliche Lauf ist ein
   Leichtlauf nur in Python (SPEC 9.1), ohne Modellkosten. Tiefenanalysen laufen, wenn überhaupt,
   über das Abo (`claude -p`). `.github/workflows/scheduled-run.yml` entfällt, weil GitHub Actions
   nur mit API-Schlüssel ginge (SPEC 15.2).
2. **Schalter bei Luca.** `stockagent zeitplan an|aus` schreibt `state/zeitplan.yaml`. Ohne „an“
   bricht jeder Lauf nach Zeitplan mit Hinweis ab. Einrichtung auf dem Mac mit
   `stockagent zeitplan einrichten [--uhrzeit HH:MM] [--laden]` (launchd, Rechner muss laufen),
   alternativ eine geplante Aufgabe der Claude-Desktop-App mit demselben Befehl
   `uv run stockagent run --profile scheduled --yes` (SPEC 15.2).
3. **Ablauf** (`zeitplan.py`): Sperre gegen zwei gleichzeitige Läufe, Universum höchstens
   wöchentlich, Noten der Beobachtungsliste immer neu (Daten werden dabei nachgeladen), Ereignisse
   seit dem letzten Lauf nach Zeitplan, Markierung der Titel, Abgleich der Eskalationen mit
   GitHub, Benachrichtigung, Laufübersicht unter `runs/_laeufe/<lauf_id>/` wie bei jedem Lauf. Ein
   Fehler bei Universum, GitHub oder einem Kanal hält den Lauf nicht an und steht im Bericht
   (HR-16). Lucas letzte eigene Anfrage (`state/last_request.yaml`) bleibt unberührt.
4. **Ereignisse** (SPEC 9.2): neuer Bericht und Restatement bei Titeln der Beobachtungsliste,
   Insider-Cluster-Käufe am offenen Markt bei allen bewerteten Titeln (Handelstag höchstens 30
   Tage vor dem letzten Lauf), Noten- und Kategoriewechsel der Beobachtungsliste. Schon gemeldete
   Ereignisse (gleiche Art und gleicher Text am Titel) werden nicht wiederholt. Markierungen in
   `state/markierungen.yaml`, im Dashboard als Fähnchen am Titel.
5. **Tiefenanalyse nur auf Wunsch.** Das Profil `scheduled` hat Tiefe „schnell“. Stellt Luca sie
   auf „standard“ oder „tief“, bekommen Ereignistitel eine Tiefenanalyse bis zur Grenze je Lauf
   (HR-18), über die Warteschlange des Dashboards oder nacheinander über `claude -p`.
6. **Benachrichtigung** (SPEC 13.4): immer als Datei `nachricht.txt`, dazu wählbar Mitteilung
   auf dem Mac (`osascript`, Standard), Telegram oder E-Mail. Zugänge nur über
   Umgebungsvariablen (`.env`), nie in `config/`.
7. **Eskalationen als GitHub-Issues** (SPEC 16.14, Default von SPEC 19 Nr. 5): ein Issue je
   offenem Fall mit Label `escalation`, Streitpunkte mit beiden Werten. Der nächste Lauf übernimmt
   nur Kommentare des Repository-Eigentümers in fester Form (`/entscheidung annehmen|ablehnen|
   neu-pruefen <Begründung>`): annehmen = freigeben, ablehnen = verwerfen, danach wird das Issue
   geschlossen. Andere Texte und Kommentare anderer werden ignoriert (HR-17). Abschaltbar mit
   `zeitplan.github_issues: false`.

## Abweichungen und Grenzen

- Ad-hoc-Mitteilungen zu Prognosesenkung und Prüferwechsel (SPEC 9.2 Warnsignal) haben keine
  strukturierte Quelle und werden nicht geprüft. Restatements werden erkannt. Der Bericht nennt
  die Lücke.
- „neu-pruefen“ wird vermerkt, startet aber keine neue Prüfung. Die Übernahme der Entscheidung
  in den Goldstandard (SPEC 16.14) ist nicht gebaut.
- Insider-Cluster zählen nur bei schon bewerteten Titeln, weil nur dort Form-4-Daten geladen sind.
- Die Abnahme „drei Läufe hintereinander“ ist mit Attrappen für Netz, GitHub und Mitteilung
  getestet. Ein echter Lauf auf Lucas Mac folgt, sobald dort Daten geladen sind.

## Fragen an Luca

1. Soll der Zeitplan eingeschaltet werden, und zu welcher Uhrzeit (Standard 07:30)?
2. Welche Kanäle für die Benachrichtigung (Standard: Datei und Mitteilung auf dem Mac)?
3. Eskalationen als GitHub-Issues: so lassen (Standard laut SPEC) oder ausschalten?
