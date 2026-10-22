# ADR 0016: Korrekturen aus dem Review vom 22.10.2026

Status: angenommen (22.10.2026, Lucas Auftrag „behebe Punkte 1 bis 10 und mach einen PR“).

## Kontext

Das Review des ganzen Programms nach Bauschritt 12 fand 15 Befunde (technisch, wirtschaftlich,
Bedienung). Luca hat die Punkte 1 bis 10 sowie README und die Punkte 13 bis 15 beauftragt.

## Entscheidungen

1. **Zuordnung vor der Vergleichsgruppe.** Sind mehr als 10 Prozent der US-Aktien des Universums
   nie der SEC zugeordnet (frische Installation), ordnet `bewerten` zuerst alle zu
   (`sec update`, 30 bis 60 Minuten, einmalig). Die Meldung „Vergleichsgruppe zu klein“ nennt die
   Zahl der zugeordneten Aktien und den Befehl.
2. **Netz robuster.** Abgebrochene Übertragungen und kurze Ausfälle (IncompleteRead,
   RemoteDisconnected, DNS) werden wie Zeitüberschreitungen wiederholt, 5 Versuche mit 2, 4, 8 und
   16 Sekunden Pause. Eine Vergleichsfirma, die nicht lädt, wird übersprungen statt die ganze
   Bewertung abzubrechen.
3. **Tiefenanalyse wirkt auf die Kategorie zurück** (SPEC 6.5, HR-13): Liste, Filter, Läufe und
   Zeitplan zeigen höchstens die Kategorie aus `decision.json` der letzten abgeschlossenen
   Analyse (nach Lucas Entscheidung dessen Kategorie). Eskaliert macht aus Attraktiv,
   Beobachten und Neutral „Eskaliert“. Die gespeicherte Note bleibt deterministisch, die
   Unternehmensseite nennt das Ergebnis.
4. **Liegen gebliebene Tiefenanalysen** werden vor jedem neuen Start auf Zeitlimit und
   Konfiguration geprüft und abgebrochen (`orchestrator.aufraeumen`), statt die Grenze HR-18 zu
   belegen.
5. **Aktuelle Aktienzahl** für den aktuellen Börsenwert, siehe Methodik 5.8.
6. **Nie gebaute Teile:** Hochinflationsländer mit Kappung auf K3, Quellensteuer als Information
   auf der Unternehmensseite, statisches Dashboard für den Lesemodus
   (`stockagent dashboard --html <datei>`), Stand der Regeln ACC-01 bis ACC-14 in der
   Methodik-Ansicht. Die Listen in `config/hyperinflation.yaml` und `config/withholding_tax.yaml`
   tragen `geprueft: false`, bis Luca sie gegen die genannten Quellen geprüft hat. Die offenen
   ACC-Regeln brauchen den PDF-Rückfall (A2) und bleiben offen.
7. **ESEF-Melder als Vergleichsfirmen** ab „Scorecard in der Region“, Umsatz für die
   Größenauswahl aus dem eigenen Bericht in USD.
8. **Zinsdeckung je Scorecard** (Versorger und Immobilien 1,5), Schwelle aus `config/`.
9. **Säule Momentum nur aus dem Kurs.**
10. **Schranken:** Zahlen-Gate erkennt ausgeschriebene Zahlen vor Einheiten und
    Vervielfachungen, Formulierungs-Gate mehr Empfehlungsfloskeln.

## Nicht umgesetzt

- Befund 11 (Freitext-Abfrage per GET aus fremden Webseiten) war nicht beauftragt.
- Reale Zeitreihen in Hochinflationsländern (SPEC 5.2 Nr. 8 „real betrachtet“), Quellensteuer im
  Bericht der Tiefenanalyse.
