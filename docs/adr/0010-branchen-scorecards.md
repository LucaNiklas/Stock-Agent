# ADR 0010: Branchen-Scorecards (Bauschritt 8)

Status: angenommen (21.10.2026, im Rahmen von Lucas Auftrag „bis Bauschritt 8 in einem Durchlauf,
beste Option wählen“). Abweichungen von der Spezifikation sind unten einzeln benannt.

## Kontext

SPEC 3.11 verlangt eigene Scorecards für Banken, Versicherer, Immobilien, Versorger, Zykliker,
Holdings und Wachstumsfirmen ohne Gewinn, mit eigenen Kennzahlen, Gewichten und
Bewertungsverfahren. Bis Schritt 7 bekamen diese Firmen Status N („folgt in Schritt 8“). Die
Daten kommen weiter aus den XBRL-Berichten (Company Facts der SEC, ESEF). Geprüft wurde am
20.10.2026, welche Größen dort ohne Dimension stehen: bei JPMorgan, Bank of America, Wells Fargo,
HSBC, Barclays, ING, Santander, Deutsche Bank, Travelers, Allstate, Progressive, Chubb, MetLife,
Prologis, Realty Income, Simon Property, NextEra, Duke und Southern.

## Entscheidung

1. **Kennzahlen** in `core/branchenkennzahlen.py`, über den Rechenweg mit Prüfpunkten, Einträge in
   `config/metrics.yaml` (methodology_version 1.7). Neue Größen in `config/concept_map.yaml` 1.3.
2. **Banken:** ROTE (Ergebnis der Stammaktionäre zu durchschnittlichem materiellem Eigenkapital),
   Kosten-Ertrags-Verhältnis, TCE-Quote, Risikokosten, Ausfallquote, Vorsorgebestand, Einlagenanteil,
   materieller Buchwert je Aktie (Wachstum über `cagr_5j`), Kurs zu materiellem Buchwert und der
   Abstand dazu nach der Residualgewinnlogik: gerechtfertigt = (ROTE − g) / (Ke − g), g = 0.
   Geprüft an JPMorgan 2025: ROTE 19,8 % (JPMorgan meldet rund 20 %), Kosten-Ertrags-Verhältnis
   52,4 % (gemeldet 52 %).
3. **Versicherer:** Schadenquote, Reserveabwicklung, Kapitalanlagerendite, Buchwert je Aktie,
   Kurs-Buchwert und sein Abstand zum gerechtfertigten Wert (ROE statt ROTE). Geprüft an Progressive.
4. **Eigenkapitalkosten von Banken und Versicherern:** rf + Beta der Branche laut Damodaran (wie
   gemessen) * Risikoprämie. Das Hamada-Verfahren der übrigen Firmen setzt Schulden als
   Finanzierung voraus, bei Banken sind sie Rohstoff des Geschäfts.
5. **Immobilien:** FFO nach NAREIT aus XBRL angenähert (Ergebnis + Abschreibungen +
   Wertminderungen − Verkaufsgewinne), FFO je Aktie, FFO-Rendite, Ausschüttung zu FFO,
   Beleihungsquote, EV/EBITDA. Geprüft an Realty Income: 4,27 USD FFO je Aktie.
6. **Versorger:** EV/EBITDA, Dividendendeckung, dazu Verschuldung, Zinsdeckung, Investitionsquote.
7. **Zykliker:** Qualität über das Mittel der letzten bis zu 10 Jahre (neue Trendstatistik
   `mittel`), Bewertung über das normalisierte EV/EBIT, Bilanz stärker gewichtet (eigene
   Säulengewichte).
8. **Wachstum ohne Gewinn:** Mohanram G-Score beim Benoten gegen den Median der Vergleichsgruppe
   (`core/gscore.py`, Anteil erfüllter an vorhandenen Signalen, mindestens 4), Bruttomarge,
   Liquiditätsreichweite (Obergrenze 120 Monate), Verwässerung, EV/Umsatz zu Wachstum. Konfidenz
   eine Stufe tiefer, weil der G-Score für diese Firmen nur ein Hilfsmaß ist (SPEC 3.11).
   Zuordnung: EBIT-Marge in beiden letzten Jahren negativ und Umsatzwachstum über 15 % je Jahr
   (3 Jahre).
9. **Holdings:** at-equity-Beteiligungen über 50 % der Bilanzsumme (`holding_share`). Status N mit
   Grund, weil die Summe der Teile Marktwerte der Beteiligungen braucht.
10. **Je Scorecard** in `config/scorecards.yaml`: welche Kappungen gelten, Multiples der
    Bewertungsbedingung (mit Richtung), ob der Reverse-DCF zählt, der Risikoeingang Verschuldung
    und eigene Säulengewichte. Zinsdeckung, Altman Z und Verschuldung zu EBITDA kappen bei Banken
    und Versicherern nicht. Bei Versorgern und REITs kappen nur Zinsdeckung und Beneish, weil
    negativer FCF bei hoher Verschuldung dort das Geschäftsmodell ist.
11. **Vergleichsgruppe** wie bisher innerhalb der Scorecard nach SIC. Für Wachstumsfirmen und
    Holdings ist das die Scorecard ihres SIC-Codes (Branchenmedian beim G-Score, wie bei Mohanram).

## Abweichungen und offen

- *Abweichung:* CET1-Quote, Quote notleidender Kredite, Combined Ratio, Solvency- und RBC-Quote,
  regulierte Kapitalbasis, NAV und Leerstand stehen nicht ohne Dimension in den XBRL-Daten.
  Ersatz: TCE-Quote, Ausfallquote, Schadenquote, Kurs-Buchwert. Die übrigen fehlen, bis es eine
  Quelle gibt (Aufsichtsmeldungen, Bericht über Agenten).
- *Abweichung:* Streuungen im G-Score aus Jahreswerten statt Quartalen.
- Banken nach IFRS melden meist keine Summe der zinsunabhängigen Erträge: Kosten-Ertrags-Verhältnis
  dort unknown.
- FFO enthält Abschreibungen auf nicht immobilienbezogene Werte, Verkaufsgewinne fehlen, wo die
  Firma ein eigenes Konzept nutzt (Prologis): FFO dann zu hoch (Vermerk im Rechenweg).
- NACE-Codes: Firmen ohne SIC (ESEF-Melder ohne SEC-Gegenstück) landen in der Standard-Scorecard.
- Abnahme: siehe unten.
