# ADR 0007: Note, Vergleichsgruppe und Oberfläche (Bauschritt 5)

Status: angenommen (19.10.2026, im Rahmen von Lucas Auftrag „bis Bauschritt 8 in einem Durchlauf,
beste Option wählen“). Abweichungen von der Spezifikation sind unten einzeln benannt.

## Kontext

SPEC 6 beschreibt Note, Konfidenz, Risiko und Kategorie, ADR 0005 legt fest, dass nur auf Anfrage
bewertet wird (angefragter Titel plus 15 bis 50 Vergleichstitel). Offen waren: woher der Umsatz
aller Kandidaten für die Auswahl kommt, wie die Risikoklasse ohne Universumslauf gebildet wird,
welche Kennzahlen in die Scorecard Standard gehen und wie die Indexstufe ohne geprüfte Quelle
zustande kommt.

## Entscheidung

1. **Umsatz aller Kandidaten:** SEC-Schnittstelle „XBRL Frames“ (`data.sec.gov/api/xbrl/frames`),
   je Umsatzkonzept aus `config/concept_map.yaml` ein Abruf für das letzte volle Kalenderjahr
   (CY2025: rund 2.250 Firmen). Je Firma zählt das erste Konzept der Liste. Die Daten werden 30
   Tage verwendet. Kein Kurs nötig, also kein Abruf für Titel außerhalb der Gruppe.
2. **Vergleichsgruppe:** dieselbe Scorecard, dann stufenweise breiter, bis mindestens 15 Titel
   da sind: Unterbranche in der Region, Unterbranche weltweit, Scorecard in der Region, Scorecard
   weltweit. Bei mehr als 50 die mit dem kleinsten Abstand |ln(Umsatz / eigener Umsatz)|. Die
   gewählte Stufe steht bei jeder Note. Daten der Gruppe werden geladen, wenn der letzte
   Kennzahlenlauf älter als 7 Tage ist.
3. **Note:** je Kennzahl der Rang in der Gruppe einschließlich der Firma selbst,
   (kleiner + 0,5 · gleich) / n · 100, bei „niedriger ist besser“ 100 minus das. Säulenwert =
   Mittel der vorhandenen Ränge, Gesamtwert = gewichtetes Mittel der Säulen mit Wert (das
   Gewicht fehlender Säulen, heute Insider, verteilt sich). Kappungen nach SPEC 6.2 Nr. 6,
   zusätzlich bei Abdeckung unter 70 %. Alles über den Rechenweg mit CP-07.
4. **Scorecard Standard (`config/scorecards.yaml`):**
   Qualität (Bruttogewinn je Vermögen, ROIC, FCF-Marge, Streuung der EBIT-Marge, Piotroski),
   Bewertung (EV/EBIT, FCF-Rendite, Wachstumslücke, Sicherheitsmarge zum Base-DCF, alle mit
   aktuellem Kurs), Stabilität (Nettoverschuldung/EBITDA, Zinsdeckung, Altman Z'', Fälligkeiten
   12 Monate), Wachstum (Umsatz-CAGR 5 Jahre, FCF je Aktie CAGR 5 Jahre, Steigung von EBIT- und
   FCF-Marge), Kapitalallokation (Aktionärsrendite, Veränderung der Aktienzahl 3 Jahre,
   Akquisitionsintensität). Insider folgt in Schritt 9.
5. **Wachstumslücke (`growth_gap`):** implizites Wachstum des Reverse-DCF minus Umsatz-CAGR
   5 Jahre. *Abweichung:* SPEC 3.6 nennt das historische FCF-Wachstum. FCF schwankt zu stark,
   eine CAGR über einen negativen Anfangswert ist nicht definiert. Umsatz ist die stabilere
   Vergleichsgröße.
6. **Risikoklasse:** *Abweichung:* SPEC 6.4 bildet Quintile über das Universum. Ohne
   Universumslauf (ADR 0005) gelten feste Schwellen in `config/scoring.yaml`, je Eingang
   (Volatilität 3 Jahre, größter Rückgang 5 Jahre, Verschuldung, Amihud-Illiquidität, Streuung
   der EBIT-Marge, Größe) Stufe 1 bis 5, Mittel gerundet. Kurse vorher in EUR umgerechnet.
   Mindestens drei Eingänge, sonst kein Risiko.
7. **Zykliker:** *Abweichung:* SIC 2840 bis 2844 (Körperpflege, Waschmittel, etwa Procter &
   Gamble) zählt nicht als Zykliker, obwohl es im Chemie-Bereich liegt.
8. **Scorecards außer Standard** geben bis Schritt 8 Status N mit Grund.
9. **Indexstufe:** *Abweichung:* SPEC 7.9 sieht ETF-Bestandslisten als Quelle vor. Die Domains
   der Anbieter sind noch nicht frei und je Index ungeprüft. Bis dahin importiert Luca eine
   Bestandsliste (CSV mit ISIN-Spalte) von Hand: `stockagent tiers import <index> <datei>`.
   Jeder Stand wird mit Datum und SHA-256 gespeichert, ausgeschiedene Titel behalten ihren alten
   Zeitraum (HR-07). Ohne Import haben alle Titel Stufe 4.
10. **Dashboard:** lokaler Server nur auf 127.0.0.1 (Python-Standardbibliothek, kein
   zusätzliches Paket). Anfragen mit fremdem Host- oder Origin-Kopf werden abgelehnt (Schutz
   gegen DNS-Rebinding). Freitext über eine feste Wortliste (Land, Region, Stufe, Note, Branche),
   die Übersetzung mit `claude -p` folgt in Schritt 11. Stern und Notizen in `state/`.

## Folgen

- Eine Note ist immer relativ zur gewählten Gruppe. Bei Stufe „Scorecard weltweit“ ist sie
  weniger aussagekräftig, das zeigt die Unternehmensseite.
- Die festen Risikoschwellen werden ersetzt, sobald ein Lauf über alle Titel existiert.
- Die Notenkontrolle (SPEC 14.2) beginnt mit dem ersten Tagesstand in `grade_snapshots`.
