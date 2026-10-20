# ADR 0009: IFRS-Berichte, ESEF, Hinterlegungsscheine und Währung (Bauschritt 7)

Status: angenommen (20.10.2026, im Rahmen von Lucas Auftrag „bis Bauschritt 8 in einem Durchlauf,
beste Option wählen“). Abweichungen von der Spezifikation sind unten einzeln benannt.

## Kontext

Schritt 7 soll EU-Werte über ESEF-Berichte (filings.xbrl.org) laden und mit US-GAAP vergleichbar
machen. Die Domain `filings.xbrl.org` ist in dieser Umgebung am 20.10.2026 von der
Netzwerkrichtlinie gesperrt. Erreichbar ist die SEC. Dort reichen viele große europäische Firmen
ihren Jahresbericht als 20-F nach IFRS ein, mit denselben `ifrs-full`-Konzepten wie in ESEF. Im
Universum sind 18 solche Firmen einer SEC-Nummer zugeordnet, alle als Hinterlegungsscheine
(ADRs).

## Entscheidung

1. **IFRS-Konzepte** stehen in `config/concept_map.yaml` hinter den US-GAAP-Konzepten derselben
   Größe. Ein Bericht enthält nur eine Taxonomie, die Regel „erstes Konzept mit Wert“ bleibt.
   Geprüft gegen die 20-F-Berichte 2025 von SAP, Novartis, Novo Nordisk, Sanofi, Unilever, Shell,
   GSK, Philips, Diageo und BP. Dieselbe Zuordnung gilt später für ESEF.
2. **Umsatz ohne Gesamtsumme** (Novartis, Sanofi melden Produktumsatz und sonstige Erlöse
   getrennt): Umsatz = Bruttoergebnis + Umsatzkosten bei gleicher Periode und Währung
   (`core/abgeleitet.py`, Quelle im Rechenweg).
3. **Geschäftsjahr** nur mit Umsatz, Bruttoergebnis oder Ergebnis als Jahreswert. Sonst machte
   ein Planwert im Anhang (Diageo: erwartete Pensionsbeiträge bis 30.06.2026) ein leeres Jahr.
4. **Finanzschulden IFRS:** `Borrowings` (Weg A) gegen `LongtermBorrowings` plus kurzfristig
   fällige Kredite (Weg B), CP-04. Kurzfristige Kredite und Commercial Paper sind in Borrowings
   enthalten und werden nicht addiert. Bei GSK ist Borrowings nur der langfristige Teil: CP-04
   stoppt, die Größe ist unknown statt falsch.
5. **Leasing IFRS (ACC-01):** Leasing ohne eigene kurz- und langfristige Bilanzzeile gilt als in
   den Finanzschulden enthalten und wird nicht noch einmal addiert (Vermerk
   `LEASING_IN_SCHULDEN`). Geprüft an Shell: Gesamtschulden 75,6 Mrd. USD enthalten 28,9 Mrd.
   USD Leasing (20-F 2025 Seite 261), Nettoverschuldung laut Shell 45,7 Mrd. USD (Seite 37),
   hier 45,4 Mrd. USD (Unterschied: Shells Anpassung um Sicherungsgeschäfte).
6. **Investitionen:** Wo nur ein Posten für Sachanlagen und immaterielle Werte gemeldet ist (SAP,
   BP) oder „sonstige langfristige Vermögenswerte“ (Shell), gilt dieser. Immaterielle
   Investitionen werden dann nicht ein zweites Mal abgezogen (`capex_inkl_immateriell`).
7. **Gezahlte Zinsen unter Finanzierung (ACC-04)** werden vom operativen Cashflow abgezogen.
8. **Hinterlegungsscheine:** Aktien je Schein aus dem Börsennamen der Deutschen Börse
   („SP.ADR/6“ = 6 Aktien, „ADR 1/2“ = ½ Aktie), sonst Festlegung in
   `state/adr_verhaeltnis.yaml`. Kurs je Stammaktie = Kurs je Schein in Berichtswährung / Aktien
   je Schein, im Rechenweg mit Quelle. Für Hinterlegungsscheine gilt die US-Notierung als
   Heimatbörse der Kursquelle (vorher wählte die Zuordnung bei BP und Diageo eine Londoner Zeile).
9. **Vergleichsgruppe:** Steht eine Firma nicht in den Frames der SEC (Umsatz in anderer Währung),
   gilt ihr eigener Umsatz zum EZB-Kurs in USD für die Auswahl nach ähnlichem Umsatz.
10. **Normalisierungsregeln** in `config/accounting_adjustments.yaml` mit Status je Regel: aktiv
    sind ACC-01 (teilweise), ACC-04, ACC-06, ACC-10 (teilweise), ACC-11, ACC-13 (teilweise),
    ACC-14. Offen sind die Regeln, die Anhangangaben brauchen.

11. **ESEF (nach Freigabe der Domain am 20.10.2026):** `data/sources/esef.py` und
    `esef_update.py` laden je LEI die letzten Jahresberichte als xBRL-JSON von filings.xbrl.org.
    Perioden sind halboffen („2025-01-01/2026-01-01“ = Jahr bis 31.12.2025), Werte mit
    Dimensionen bleiben außen vor, Veröffentlichung = Tag der Aufnahme bei filings.xbrl.org.
    Emittent `lei:<LEI>`. Geprüft an ASML (49 von 52 Kennzahlen), LVMH, TotalEnergies, Enel,
    Iberdrola. `bewerten` versucht ESEF, wenn es keinen SEC-Melder gibt.
12. **Emittent je ISIN über die LEI:** erst die SEC-Zuordnung der ISIN, dann ein ESEF-Emittent
    mit derselben LEI, dann ein SEC-Melder mit derselben LEI. So hat die deutsche SAP-Aktie
    (DE0007164600) die Daten des 20-F und einen Xetra-Kurs in EUR (50 von 52 Kennzahlen).
13. **Aktienzahl aus dem Ergebnis je Aktie**, wenn ESEF keine Aktienzahl meldet (TotalEnergies,
    Enel): Ergebnis der Aktionäre / verwässertes Ergebnis je Aktie, mit Vermerk.
14. **Zins GBP:** Bank of England, Serie IUDMNPY (10 Jahre, täglich).

## Abweichungen und offen

- *Abweichung:* filings.xbrl.org führt **keine deutschen Berichte** (0 Einreichungen mit Land DE,
  Stand 20.10.2026), weil das Unternehmensregister nicht angebunden ist. Deutsche Firmen haben
  nur Daten, wenn sie bei der SEC melden (SAP). Für die übrigen DAX-Werte braucht es eine andere
  Quelle (Frage an Luca).
- Firmeneigene Konzepte (etwa TotalEnergies für Investitionen, LVMH für Abschreibungen) werden
  nicht zugeordnet: die Größe bleibt unknown statt geraten.
- PDF-Rückfall mit Docling und A2 (SPEC 7.4) fehlt: Ohne ESEF und ohne freigegebene IR-Seiten der
  Emittenten gibt es keine PDFs zu verarbeiten, und Docling braucht mehrere Gigabyte Pakete.
- Risikofreier Zins für CHF fehlt (die Reihen der SNB auf data.snb.ch enden im Juli 2025) und
  für DKK (api.statbank.dk nicht erreichbar): WACC und Bewertungsverfahren dort unknown mit Grund. SPEC 5.2 Nr. 6 (Umrechnung über
  die Inflationsdifferenz) bleibt offen.
- Wechsel der Berichtswährung (Diageo GBP zu USD ab 2025): Rechnungen über mehrere Jahre stoppen
  an CP-01. Eine Umrechnung der Vorjahre folgt mit SPEC 5.2.
- Abnahme „10 DAX-Werte“ ist so nicht erfüllbar: nur SAP hat Daten (über das 20-F). Die Abnahme
  läuft hier über 10 europäische 20-F-Melder und 5 ESEF-Firmen aus NL, FR, IT, ES.
