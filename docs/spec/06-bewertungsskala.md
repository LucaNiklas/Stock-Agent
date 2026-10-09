## 6. Bewertungsskala

### 6.1 Drei getrennte Achsen

Jedes Unternehmen erhält drei Angaben, die immer zusammen angezeigt werden, etwa "B · K2 · R3".

| Achse | Frage | Werte |
|---|---|---|
| Note | Wie attraktiv ist das Unternehmen im Vergleich zu seiner Vergleichsgruppe, gemessen an Qualität, Bewertung, Stabilität, Wachstum, Kapitalallokation und Insider-Verhalten? | A bis E, dazu N für "nicht bewertbar" |
| Konfidenz | Wie belastbar ist diese Note? | K1 bis K4 |
| Risiko | Wie stark kann der Kurs schwanken und wie schwer ist die Position zu handeln? | R1 bis R5 |

Die Trennung ist Absicht. Eine gute Note auf dünner Datenbasis ist eine andere Aussage als dieselbe Note auf geprüfter Datenbasis. Wer beides zu einer Zahl verrechnet, versteckt die Unsicherheit. Risiko fließt nicht in die Note ein, weil die Forschung zu niedrig volatilen Aktien (Ang, Hodrick, Xing und Zhang 2006, Journal of Finance. Frazzini und Pedersen 2014, Journal of Financial Economics) keinen verlässlichen Renditeaufschlag für höheres Risiko findet. Risiko wird deshalb getrennt angezeigt.

### 6.2 Note

**Säulen und Default-Gewichte (Scorecard Standard)**

| Säule | Gewicht | Kennzahlen (Auswahl, vollständig im Register) |
|---|---|---|
| Qualität | 25 % | gp_to_assets, roic, fcf_margin, Margenstabilität, Piotroski F |
| Bewertung | 25 % | ev_ebit, fcf_yield, Abstand implizites Wachstum zur Historie, Sicherheitsmarge |
| Finanzielle Stabilität | 15 % | net_debt_to_ebitda, interest_coverage, Altman-Zone, debt_maturity_12m |
| Wachstum und Trend | 15 % | revenue_cagr_5y, fcf_per_share_cagr_5y, Theil-Sen-Steigung der Kernkennzahlen |
| Kapitalallokation | 10 % | shareholder_yield, share_count_change_3y, acquisition_intensity, ROIC auf Zuwachs |
| Insider | 10 % (höchstens 15 %) | Signal aus 3.8. Ohne Insider-Daten wird das Gewicht auf die anderen Säulen verteilt |

Die anderen Scorecards nutzen dieselben sechs Säulen mit eigenen Kennzahlen und Gewichten in `config/scorecards.yaml`. Banken bewerten etwa unter "Finanzielle Stabilität" die CET1-Quote und unter "Qualität" die ROTE.

**Rechenweg**

1. Jede Kennzahl wird in ein Perzentil (0 bis 100) innerhalb der Vergleichsgruppe zum Analysedatum umgerechnet. Vergleichsgruppe ist dieselbe Scorecard, dieselbe Branche und dieselbe Region (Europa, Nordamerika, Asien-Pazifik, Schwellenländer). Hat sie weniger als 15 Mitglieder, wird stufenweise erweitert (Branche global, dann Scorecard in der Region, dann Scorecard global). Die genutzte Stufe steht im Bericht.
2. Rangbasierte Standardisierung ist robust gegen Ausreißer und unabhängig von Einheit und Währung. Sie ist in der Faktorforschung üblich, etwa bei Asness, Frazzini und Pedersen ("Quality Minus Junk", 2019) und Asness, Moskowitz und Pedersen ("Value and Momentum Everywhere", 2013, Journal of Finance).
3. Die Richtung jeder Kennzahl steht im Register (höher ist besser, niedriger ist besser oder Zielband, etwa beim Current Ratio).
4. Säulenwert ist der Mittelwert der Kennzahl-Perzentile der Säule. Fehlende Kennzahlen werden nicht geschätzt (HR-05). Die Gewichte innerhalb der Säule werden auf die vorhandenen Kennzahlen verteilt.
5. Gesamtwert ist der gewichtete Mittelwert der Säulen.
6. Absolute Kappungsgrenzen, weil Perzentile relativ sind und in einer schwachen Vergleichsgruppe auch der Beste schwach sein kann.

| Bedingung | Höchstwert |
|---|---|
| Stopp-Flag aus 3.9 | 49 (D) |
| Altman Z in der Gefahrenzone (Scorecard Standard) | 64 (C) |
| FCF in drei Jahren negativ und Nettoverschuldung über dem Vierfachen des EBITDA | 49 (D) |
| Abdeckung unter 70 Prozent der gewichteten Kennzahlen | 64 (C) |
| Beneish über Schwelle ohne Entkräftung durch F1 | 64 (C) |

7. Umrechnung in die Note.

| Note | Wert | Bedeutung |
|---|---|---|
| A | 80 bis 100 | sehr attraktiv im Vergleich zur Gruppe |
| B | 65 bis 79 | attraktiv |
| C | 50 bis 64 | neutral |
| D | 35 bis 49 | unattraktiv |
| E | 0 bis 34 | meiden |
| N | | nicht bewertbar, Grund angegeben |

Die Note ist ein relativer Rang und keine Renditeprognose (siehe McLean und Pontiff in Abschnitt 1).

### 6.3 Konfidenz

| Stufe | Bedingungen (alle müssen erfüllt sein) |
|---|---|
| K1 sehr belastbar | Primärquelle XBRL oder doppelt geprüfte Extraktion, Quellenabgleich bestanden, mindestens 8 Jahre Historie, Abdeckung mindestens 90 Prozent, IFRS oder US-GAAP, Größenklasse Small oder größer |
| K2 belastbar | Quellenabgleich bestanden, mindestens 5 Jahre Historie, Abdeckung mindestens 80 Prozent, IFRS oder US-GAAP, Größenklasse Small oder größer |
| K3 eingeschränkt | mindestens 3 Jahre Historie und Abdeckung mindestens 70 Prozent. Typisch für lokale Standards, nur eine Datenquelle, Micro- und Nano-Caps, Hochinflation |
| K4 schwach | alles darunter. Die Note wird grau angezeigt und erscheint nie in den oberen Ranglisten |

### 6.4 Risikoklasse

Eingänge sind die annualisierte Volatilität der Tagesrenditen in EUR über 3 Jahre, der größte Kursrückgang über 5 Jahre, die Verschuldung (scorecardspezifisch), die Amihud-Illiquidität, die Größenklasse und die Volatilität des operativen Ergebnisses. Jeder Eingang wird in ein Quintil des Gesamtuniversums eingeordnet (1 bis 5). Die Risikoklasse ist der gerundete Mittelwert, R1 sehr niedrig bis R5 sehr hoch.

Die Risikoklasse ist reine Information. Sie leitet keine Positionsgröße ab (HR-15).

### 6.5 Kategorien

Die Kategorie ordnet ein Unternehmen ein. Sie ist keine Kauf- oder Verkaufsempfehlung (HR-15) und entsteht deterministisch (HR-13).

| Kategorie | Bedingung |
|---|---|
| Attraktiv | Note A oder B, Konfidenz K1 oder K2, keine Stopp-Flags, Bewertungsbedingung aus 3.6 erfüllt, Hysterese aus 9.5 erfüllt. Wurde eine Tiefenanalyse durchgeführt, muss sie bestanden sein, sonst gilt "Eskaliert" |
| Beobachten | Note B mit zu hoher Bewertung, Note C mit Aufwärtstrend oder Note A mit K3 |
| Neutral | Note C ohne Aufwärtstrend |
| Unattraktiv | Note D oder E |
| Eskaliert | Prüfung der Tiefenanalyse nicht bestanden oder Jury uneinig, wartet auf Luca |
| Nicht bewertbar | Status N mit Grund |

Alle Schwellen sind Defaults in `config/scoring.yaml`. Sie werden nach der Notenkontrolle (Abschnitt 14) überprüft, aber nie an dem Zeitraum angepasst, auf dem sie getestet werden.

### 6.6 Kalibrierung der Skala

Nach 24 Monaten Notenkontrolle (14.2) prüft das System, ob die Noten die Folgeentwicklung ordnen. Gemessen wird die Rangkorrelation (Spearman) zwischen Note und Rendite der folgenden 12 Monate sowie die Rendite je Notenstufe. Ist die Ordnung nicht monoton (A besser als B besser als C), wird die Gewichtung in einem getrennten Zeitraum neu geprüft und die Änderung als neue Methodik-Version eingeführt.

### 6.7 Darstellung

Die Note erscheint als Buchstabe in einem farbigen Kästchen, die Konfidenz als Füllstand mit vier Segmenten, die Risikoklasse als Ziffer. Farbe trägt nie allein die Bedeutung. Jede Note ist anklickbar und zeigt die Zerlegung in Säulen und Kennzahl-Perzentile samt Vergleichsgruppe.
