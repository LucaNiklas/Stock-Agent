## 5. Währungen

### 5.1 Grundlagen

| Befund | Quelle | Folgerung |
|---|---|---|
| Währungsrisiko eines Unternehmens ist die Empfindlichkeit seines Werts gegenüber Wechselkursen und hängt davon ab, wo Umsätze und Kosten anfallen, nicht von der Notierungswährung | Adler und Dumas (1984, Financial Management) | Exposure wird aus der regionalen Umsatzverteilung bestimmt |
| Wechselkurseffekte auf Unternehmenswerte sind messbar, werden vom Markt aber teils verzögert eingepreist | Jorion (1990, Journal of Business), Bartov und Bodnar (1994, Journal of Finance) | Wachstum in konstanter Währung getrennt ausweisen |
| Umrechnung nach Stichtagskurs für Bilanzposten und Durchschnittskurs für Erfolgsgrößen | IAS 21, ASC 830 | System übernimmt dieselbe Logik |
| Cashflows und Diskontsatz müssen in derselben Währung stehen. Umrechnung von Kapitalkosten über die Inflationsdifferenz | Damodaran (Investment Valuation), Fisher-Beziehung | DCF immer in Berichtswährung |
| Hochinflationsländer erfordern Indexierung der Abschlüsse | IAS 29 | Eigener Flag und Konfidenzabschlag |

### 5.2 Regeln

1. Jeder Wert wird in Originalwährung gespeichert. Umrechnungskurse liegen separat mit Datum und Quelle (EZB-Referenzkurse).
2. Verhältniskennzahlen (Margen, Renditen, Quoten) werden in Berichtswährung gerechnet und sind damit währungsneutral.
3. Bilanzposten werden zum Stichtagskurs umgerechnet, GuV- und Cashflow-Posten zum Durchschnittskurs der Periode. Der Durchschnitt entsteht aus täglichen Referenzkursen.
4. Marktkapitalisierung entsteht in Kurswährung. Für den Unternehmenswert wird die Nettoverschuldung aus der Berichtswährung zum aktuellen Kassakurs in die Kurswährung umgerechnet. Für Multiples wird die TTM-Stromgröße zum Durchschnittskurs der letzten vier Quartale umgerechnet. Kurs- und Berichtswährung weichen häufig voneinander ab, etwa wenn ein Unternehmen in USD berichtet und in EUR oder GBP notiert.
5. Wachstum wird dreifach ausgewiesen. In Berichtswährung (geht in die Note ein, weil sie die wirtschaftliche Leistung zeigt), in EUR (zeigt Lucas Erleben als EUR-Anleger) und in konstanter Währung, sofern der Bericht diese Angabe mit Beleg liefert.
6. DCF und Reverse-DCF laufen in Berichtswährung mit dem risikofreien Zins derselben Währung. Der Wert je Aktie wird zum Kassakurs in EUR umgerechnet. Liegen Annahmen in einer anderen Währung vor, wird der Diskontsatz über die Fisher-Beziehung umgerechnet. (1 + r_A) = (1 + r_B) mal (1 + π_A) / (1 + π_B), mit π als erwarteter Inflation.
7. Das Endwachstum im DCF liegt höchstens beim langfristigen nominalen risikofreien Zins der Berichtswährung.
8. Hochinflationsländer nach IAS 29 stehen in `config/hyperinflation.yaml`. Betroffene Unternehmen erhalten den Flag `hyperinflation`, höchstens Konfidenz K3, und Zeitreihen werden real betrachtet.
9. Ökonomisches Währungsexposure. Die geografische Umsatzverteilung aus dem Segmentbericht ergibt einen Umsatzwährungsmix. Auf Portfolioebene zeigt das Dashboard getrennt die Notierungswährungen und die ökonomische Umsatzherkunft, jeweils einschließlich Durchschau auf die ETFs.
10. Unterwährungen werden erkannt und umgerechnet. GBX (Pence) gegen GBP, ZAc gegen ZAR, ILA gegen ILS. Ein Faktor-100-Fehler ist der häufigste Datenfehler bei britischen Werten.
11. ADR und GDR werden über das Depotverhältnis auf die Stammaktie normiert, damit Kennzahlen je Aktie stimmen.
12. Quellensteuer auf Dividenden je Land steht in `config/withholding_tax.yaml` und erscheint im Bericht als Information.
13. Plausibilitätsprüfung INC-13. Der aus zwei Notierungen abgeleitete Wechselkurs (Kurs in EUR geteilt durch Kurs in Heimatwährung) darf höchstens 2 Prozent vom Referenzkurs abweichen. Sonst liegt ein Daten- oder Einheitenfehler vor.
