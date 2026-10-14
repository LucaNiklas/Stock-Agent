## 3. Bewertungsmethodik

Die Methodik folgt einer festen Reihenfolge. Jede Stufe ist ein eigenes Modul mit eigener Versionsnummer (`methodology_version`).

```
Universum (alle Unternehmen) -> Klassifikation (Scorecard, Größe, Liquidität)
-> Datenqualität und Konfidenz -> Normalisierung Rechnungslegung und Währung
-> Kennzahlen und Trends -> Qualitäts- und Risiko-Scores -> Bewertung
-> Note, Konfidenz, Risikoklasse für alle Unternehmen
-> Tiefenanalyse für gewählte Kategorie mit qualitativer Analyse,
   Insider-Signal, Gegenposition, Verifikation
-> Finanzieller Überblick je Unternehmen und Laufübersicht
```

### 3.1 Vollabdeckung statt Ausschluss (Stufe 1)

Jedes Unternehmen im Universum wird bewertet. Es gibt keine Mindestgröße, keinen Mindestumsatz an der Börse und keinen Branchenausschluss. Merkmale, die in Version 2 zum Ausschluss führten, wirken jetzt auf drei andere Arten. Sie senken den Konfidenzgrad (wie belastbar ist die Note) und sie erhöhen die Risikoklasse. Die Skala dazu steht in Abschnitt 6.

Die Forschung stützt diese Trennung. Fama und French (2008, "Dissecting Anomalies", Journal of Finance) zeigen, dass Mikrowerte zwar nur rund 3 Prozent des Börsenwerts, aber rund 60 Prozent aller Titel ausmachen und gleichgewichtete Ergebnisse dominieren. Hou, Xue und Zhang (2020, "Replicating Anomalies", Review of Financial Studies) finden, dass ein Großteil veröffentlichter Anomalien verschwindet, wenn man Mikrowerte richtig behandelt. Kennzahlen kleiner Firmen sind also statistisch weniger verlässlich, aber nicht wertlos. Amihud und Mendelson (1986, Journal of Financial Economics) und Amihud (2002, Journal of Financial Markets) zeigen, dass illiquide Aktien im Mittel höhere erwartete Renditen als Ausgleich für höhere Handelskosten haben. Für einen Anleger mit 15 bis 20 Jahren Horizont ist geringe Liquidität deshalb ein Kosten- und Risikomerkmal und kein Ausschlussgrund.

| Merkmal | Wirkung |
|---|---|
| Größenklasse nach Marktkapitalisierung (Nano unter 50 Mio. EUR, Micro 50 bis 300 Mio., Small 300 Mio. bis 2 Mrd., Mid 2 bis 10 Mrd., Large 10 bis 200 Mrd., Mega über 200 Mrd.) | Konfidenz (Micro und Nano höchstens K3), Risikoklasse, Vergleichsgruppe zusätzlich nach Größe |
| Illiquidität nach Amihud, ILLIQ = Mittelwert über 250 Handelstage von abs(Tagesrendite) / Tagesumsatz in EUR | Risikoklasse. Hinweis auf geringe Handelbarkeit im Bericht |
| Datenhistorie unter 5 Jahren | Konfidenz sinkt. Trendsäule mit verfügbarer Historie. Unter 2 Jahren Status "nicht bewertbar (Historie)" mit Anzeige der vorhandenen Werte |
| Going-Concern-Hinweis, versagter oder eingeschränkter Bestätigungsvermerk | Stopp-Flag, Note höchstens D (Abschnitt 6.2) |
| Lokale Rechnungslegung (HGB-Konzern ohne IFRS, J-GAAP, Ind AS, chinesische ASBE und andere) | Bewertung mit Konfidenz höchstens K3 (Abschnitt 4) |
| Banken, Versicherer, Immobilien, Holdings | eigene Scorecard (Abschnitt 3.11) |
| SPAC, Mantelgesellschaft, Fonds, ETF, Zertifikat | Status "kein operatives Unternehmen". Wird gelistet, bekommt aber keine Fundamentalnote |
| Laufendes Übernahmeangebot | Note wird berechnet, Hinweis "Kurs wird vom Angebot bestimmt" |
| Mehrfachlistings (ADR, Zweitnotiz) | technisch auf den Emittenten (LEI) zusammengeführt, alle Handelsplätze bleiben sichtbar |

"Nicht bewertbar" ist ein sichtbarer Status mit Grund. Kein Unternehmen verschwindet stillschweigend aus dem Universum.

### 3.2 Datenqualitätsprüfung (Stufe 2)

Die Ergebnisse landen als `dq_flags` am Unternehmen und bestimmen den Konfidenzgrad (6.3). Ein Stopp setzt die betroffenen Werte auf `unknown`, das Unternehmen bleibt im Universum.

1. Bilanzgleichung je Periode (Aktiva gleich Passiva, Toleranz 0,5 Prozent).
2. Konsistenz mit der XBRL-Berechnungsstruktur (Summen der Unterpositionen gleich Summenposition).
3. Einheiten und Skalierung (Tausend, Millionen) eindeutig, Währung je Wert gesetzt.
4. Periodenlogik stimmt (Geschäftsjahr mit abweichendem Stichtag korrekt zugeordnet, Quartale ergeben TTM ohne Doppelzählung).
5. Abgleich zweier unabhängiger Quellen für die Kernwerte Umsatz, operatives Ergebnis, Jahresüberschuss, operativer Cashflow, Investitionen, Bilanzsumme, Eigenkapital, Finanzschulden, Aktienanzahl. Abweichung über 1 Prozent erzeugt eine Warnung, über 5 Prozent einen Stopp.
6. Ausreißerprüfung gegen die eigene Historie auf zwei Wegen: robuster z-Wert gegen den Median der Vorjahre (Niveau) und gegen die Fortschreibung ihres Theil-Sen-Trends (Trend), Streuung jeweils über MAD mit Untergrenze, Schwelle 4. Ausreißer nur, wenn beide Wege auffallen. Ein gleichmäßiger Anstieg ist so kein Ausreißer, ein Sprung schon. Ein Ausreißer ist kein Fehler, braucht aber eine Begründung aus dem Bericht, etwa eine Übernahme.
7. Restatements erkennen. Wenn ein späterer Bericht Vorjahreswerte ändert, werden beide Fassungen gespeichert und die Änderung markiert.
8. Aktienanzahl um Splits und Aktiendividenden bereinigt.

### 3.3 Kennzahlenkatalog

Jede Kennzahl ist in `config/metrics.yaml` als Formel mit ID, Version, Eingabekonzepten und Sektorhinweisen hinterlegt. Zu jedem Eintrag gehört genau eine Funktion in `core/registry.py`, registriert über den Dekorator `@metric("id")` (18.1). Die Berechnung ruft Kennzahlen nur über diese Registry auf.

Durchschnittswerte für Bestandsgrößen sind (Anfang plus Ende) durch 2. TTM bedeutet Summe der letzten vier Quartale.

**Profitabilität**

| ID | Formel | Hinweis |
|---|---|---|
| gross_margin | Bruttoergebnis / Umsatz | Nicht bei Umsatzkostenverfahren ohne Bruttoergebnis berechenbar, dann leer lassen |
| ebit_margin | EBIT / Umsatz | |
| fcf_margin | Free Cashflow / Umsatz | |
| gp_to_assets | Bruttoergebnis / Bilanzsumme | Novy-Marx (2013), gilt als starkes Qualitätsmaß |
| roe | Jahresüberschuss / durchschnittliches Eigenkapital | Bei negativem Eigenkapital nicht definiert |
| roa | Jahresüberschuss / durchschnittliche Bilanzsumme | |
| roic | NOPAT / durchschnittliches investiertes Kapital | NOPAT = EBIT mal (1 minus Steuersatz). Investiertes Kapital = Eigenkapital plus Finanzschulden plus Leasingverbindlichkeiten minus liquide Mittel |
| dupont | ROE = Nettomarge mal Kapitalumschlag mal Hebel | Zerlegung zeigt, ob Rendite aus Marge oder Verschuldung kommt |

**Wachstum**

| ID | Formel | Hinweis |
|---|---|---|
| revenue_cagr_3y, revenue_cagr_5y | (Wert t / Wert t-n) hoch (1/n) minus 1 | Organisches Wachstum aus Bericht übernehmen, wenn verfügbar |
| eps_cagr_5y | analog auf verwässertem Ergebnis je Aktie | Durch Rückkäufe getriebenes Wachstum separat ausweisen |
| fcf_per_share_cagr_5y | analog | |
| share_count_change_3y | Aktienanzahl t / t-3 minus 1 | Verwässerung ist negativer Faktor |

**Cashflow und Ertragsqualität**

| ID | Formel | Hinweis |
|---|---|---|
| fcf | Operativer Cashflow minus Investitionen in Sachanlagen und immaterielle Werte | Unter IFRS 16 zusätzlich Tilgung von Leasingverbindlichkeiten abziehen, um mit US-GAAP vergleichbar zu sein. Beide Varianten speichern |
| fcf_conversion | FCF / Jahresüberschuss | Dauerhaft unter 0,8 ist ein Warnsignal |
| ocf_to_net_income | Operativer Cashflow / Jahresüberschuss | |
| sloan_accruals | (Jahresüberschuss minus operativer Cashflow) / durchschnittliche Bilanzsumme | Sloan (1996). Hohe Accruals gehen historisch mit schwächeren Folgerenditen einher |
| sbc_to_revenue | Aktienbasierte Vergütung / Umsatz | Bei Tech-Firmen oft wesentlicher Kostenblock, der im FCF fehlt |
| fcf_after_sbc | FCF minus aktienbasierte Vergütung | Konservative Variante |

**Bilanz und Finanzierung**

| ID | Formel | Hinweis |
|---|---|---|
| net_debt | Finanzschulden plus Leasingverbindlichkeiten minus liquide Mittel und kurzfristige Wertpapiere | Pensionsrückstellungen getrennt ausweisen (`net_debt_incl_pensions`), wichtig bei deutschen Industriewerten |
| net_debt_to_ebitda | Nettoverschuldung / EBITDA | Unter 2 komfortabel, über 3,5 erhöhtes Risiko, branchenabhängig |
| interest_coverage | EBIT / Zinsaufwand | Unter 3 ist kritisch |
| current_ratio | Umlaufvermögen / kurzfristige Verbindlichkeiten | Trend wichtiger als Niveau |
| quick_ratio | (Umlaufvermögen minus Vorräte) / kurzfristige Verbindlichkeiten | |
| equity_ratio | Eigenkapital / Bilanzsumme | |
| debt_maturity_12m | Finanzschulden fällig in 12 Monaten / liquide Mittel plus ungenutzte Kreditlinien | Refinanzierungsrisiko |

**Kapitalallokation**

| ID | Formel | Hinweis |
|---|---|---|
| payout_fcf | (Dividenden plus Rückkäufe) / FCF | Über 1 dauerhaft nur über Schulden finanzierbar |
| buyback_yield | Netto-Rückkäufe / Marktkapitalisierung | |
| shareholder_yield | Dividendenrendite plus Netto-Rückkaufrendite plus Nettoschuldenabbau / Marktkapitalisierung | |
| capex_to_depreciation | Investitionen / Abschreibungen | Dauerhaft unter 1 kann auf Substanzverzehr deuten |
| acquisition_intensity | Ausgaben für Übernahmen / operativer Cashflow (5 Jahre) | Hohe Werte machen organisches Wachstum schwer erkennbar |

**Bewertung**

| ID | Formel | Hinweis |
|---|---|---|
| enterprise_value | Marktkapitalisierung plus Nettoverschuldung plus Minderheitsanteile plus Pensionsdefizit minus nicht betriebsnotwendige Beteiligungen | Brücke einzeln speichern |
| ev_ebit | EV / EBIT (TTM und nächstes Jahr, falls Konsens verfügbar) | Vorzugskennzahl für Vergleiche über Kapitalstrukturen hinweg |
| ev_sales | EV / Umsatz | Für Firmen mit negativem EBIT |
| pe | Kurs / verwässertes EPS | Nur bei positivem Ergebnis |
| fcf_yield | FCF / Marktkapitalisierung | |
| pb | Kurs / Buchwert je Aktie | |
| dividend_yield | Dividende je Aktie / Kurs | |

Jede Bewertungskennzahl wird dreifach eingeordnet. Gegen die eigene Historie (Perzentil der letzten 10 Jahre), gegen die Vergleichsgruppe (Perzentil innerhalb der Branche, Branchenschlüssel aus SIC bei US-Werten und NACE bei EU-Werten, weil GICS lizenzpflichtig ist) und gegen den Gesamtmarkt.

### 3.4 Trend- und Zeitreihenanalyse

1. Mindestens 5, wenn verfügbar 10 Geschäftsjahre. Dazu die letzten 8 Quartale für TTM-Werte.
2. Für jede Kennzahl werden Niveau, Veränderung zum Vorjahr, 3- und 5-Jahres-CAGR, Standardabweichung und Trendsteigung (Theil-Sen-Schätzer, unempfindlich gegen Ausreißer) gespeichert.
3. Margenstabilität zählt so viel wie Margenniveau. Die Schwankungsbreite der EBIT-Marge über 10 Jahre geht in den Qualitätsscore ein.
4. Zyklische Branchen (Rohstoffe, Chemie, Halbleiter, Auto) werden über den gesamten Zyklus bewertet. Bewertungskennzahlen nutzen dort zusätzlich das durchschnittliche EBIT der letzten 7 bis 10 Jahre (`ev_ebit_normalized`).
5. Sondereffekte (Wertminderungen, Veräußerungsgewinne, Restrukturierung) werden aus dem Bericht übernommen und als bereinigte Zweitreihe gespeichert. Die unbereinigte Reihe bleibt maßgeblich, die bereinigte dient der Erklärung.
6. Vertikale Analyse je Jahr (alle Posten in Prozent vom Umsatz beziehungsweise von der Bilanzsumme) für die Detailansicht.

### 3.5 Qualitäts- und Risiko-Scores

Diese Scores sind etablierte Screening-Werkzeuge mit bekannten Grenzen. Sie gehen als Filter und Teilwerte ein, nie als alleinige Kaufbegründung.

**Piotroski F-Score (0 bis 9 Punkte, Piotroski 2000).** Je ein Punkt für ROA größer null, operativer Cashflow größer null, ROA gestiegen, operativer Cashflow größer Jahresüberschuss (bezogen auf die Bilanzsumme), langfristige Verschuldungsquote gesunken, Current Ratio gestiegen, keine neuen Aktien ausgegeben, Bruttomarge gestiegen, Kapitalumschlag gestiegen. Default-Schwelle für "solide" ist 6 oder mehr.

**Altman Z-Score.** Für produzierende Unternehmen gilt Z = 1,2 X1 + 1,4 X2 + 3,3 X3 + 0,6 X4 + 1,0 X5 mit X1 = Working Capital / Bilanzsumme, X2 = Gewinnrücklagen / Bilanzsumme, X3 = EBIT / Bilanzsumme, X4 = Marktkapitalisierung / Gesamtverbindlichkeiten, X5 = Umsatz / Bilanzsumme. Unter 1,81 liegt die Gefahrenzone, über 2,99 die sichere Zone. Für Nicht-Produzenten gilt Z'' = 6,56 X1 + 3,26 X2 + 6,72 X3 + 1,05 X4 mit X4 = Buchwert Eigenkapital / Gesamtverbindlichkeiten, Gefahrenzone unter 1,1, sichere Zone über 2,6. Das Modell stammt aus US-Daten der 1960er Jahre. Es dient als Warnlampe, nicht als Wahrscheinlichkeit.

**Beneish M-Score (8 Variablen).** M = minus 4,84 + 0,920 DSRI + 0,528 GMI + 0,404 AQI + 0,892 SGI + 0,115 DEPI minus 0,172 SGAI + 4,679 TATA minus 0,327 LVGI. Werte über minus 1,78 gelten als Hinweis auf mögliche Ergebnismanipulation und führen zur Eskalation an den Forensik-Agenten, nicht zum automatischen Ausschluss.

**Accruals (Sloan).** Höchstes Dezil innerhalb der Branche erzeugt ein Warnflag.

**Qualitätskomposit (angelehnt an Asness, Frazzini und Pedersen, "Quality minus Junk", 2019).** Vier Säulen mit Branchenperzentilen. Profitabilität (gp_to_assets, roic, fcf_margin), Wachstum (5-Jahres-Veränderung derselben Größen), Sicherheit (niedrige Verschuldung, niedrige Ergebnisvolatilität, Altman-Zone) und Ausschüttung (shareholder_yield, geringe Verwässerung). Gleich gewichtet, Ergebnis 0 bis 100.

### 3.6 Bewertung

Das System nennt nie einen einzelnen Kursziel-Wert. Es zeigt Spannen und macht sichtbar, welche Annahmen der aktuelle Kurs bereits enthält.

**Reverse-DCF (Hauptverfahren).** Gegeben sind aktueller Unternehmenswert, Kapitalkosten und Endwachstum. Gesucht ist das FCF-Wachstum der nächsten 10 Jahre, das den Kurs rechtfertigt. Diese implizite Wachstumsrate wird mit der eigenen Historie (5- und 10-Jahres-CAGR) und mit der Branche verglichen. Liegt sie weit über allem, was das Unternehmen je erreicht hat, ist die Aktie teuer, egal wie gut das Geschäft ist. Ist der FCF der Basisperiode null oder negativ, ist eine Wachstumsrate nicht definiert. Dann rechnet das System den Reverse-DCF auf Umsatzbasis (implizites Umsatzwachstum bei einer Zielmarge aus dem Branchenmedian der Scorecard) und kennzeichnet das Ergebnis. Ist auch das nicht sinnvoll, ist der Wert `unknown` mit Grund.

**DCF in drei Szenarien.** Bear, Base und Bull mit expliziten Annahmen zu Umsatzwachstum, Marge, Investitionsquote und Working Capital. Python leitet je Annahme drei Stufen aus der eigenen Historie und der Branche ab (`niedrig` = 25. Perzentil, `mittel` = Median, `hoch` = 75. Perzentil der 10-Jahres-Werte). Der Bewertungsagent A5 wählt je Szenario und Annahme eine Stufe und begründet die Wahl mit Quellen. Er schreibt keine Zahlen (HR-01). Python rechnet. Die Szenarien sind Information im Bericht und gehen nicht in Note oder Kategorie ein (HR-13). Regeln für die Rechnung:

1. FCFF-Ansatz über 10 Jahre, danach Endwert nach Gordon-Wachstumsmodell.
2. Endwachstum höchstens der langfristige risikofreie Zins der Berichtswährung, Default höchstens 2,5 Prozent.
3. Kapitalkosten (WACC) aus risikofreiem Zins (10-jährige Bundesanleihe für EUR, 10-jährige Treasury für USD, aus offiziellen Quellen geladen), Aktienrisikoprämie (Default ist die implizite Prämie nach Damodaran, monatlich aktualisiert und als Wert mit Datum gespeichert), Beta (Branchenbeta nach Damodaran bereinigt um die eigene Verschuldung, weil Einzelbetas stark schwanken) und Fremdkapitalkosten nach Steuern.
4. Sensitivitätsmatrix über WACC (plus/minus 1 Prozentpunkt) und Endwachstum (plus/minus 0,5 Prozentpunkte).
5. Anteil des Endwerts am Gesamtwert wird ausgewiesen. Über 75 Prozent erzeugt einen Hinweis, dass der Wert fast nur von Annahmen über die ferne Zukunft abhängt.
6. Brücke von Unternehmenswert zu Eigenkapitalwert mit allen Posten aus `enterprise_value`.

**Multiples.** EV/EBIT, FCF-Rendite und KGV gegen Historie und Vergleichsgruppe. Daraus eine Spanne über das 25. bis 75. Perzentil der Vergleichsgruppe.

**Zusammenführung als "Football Field".** Alle Spannen in einem Diagramm, dazu der aktuelle Kurs.

**Bewertungsbedingung (deterministisch).** Sie ist erfüllt, wenn die implizite Wachstumsrate im Reverse-DCF unter der 5-Jahres-Historie liegt oder der Kurs mindestens 15 Prozent (`min_discount_to_multiples`) unter dem Median der Multiples-Spanne liegt. Beide Größen entstehen ohne Sprachmodell. Die DCF-Szenarien von A5 können die Bedingung nur verschärfen: Liegt der Kurs über dem Bull-Szenario, gilt sie als nicht erfüllt (Übergang `downgrade`, HR-13).

### 3.7 Qualitative Analyse

Die qualitative Analyse liest Textteile der Berichte. Jede Aussage braucht eine Belegstelle.

| Thema | Leitfrage | Typische Quelle |
|---|---|---|
| Geschäftsmodell | Womit verdient das Unternehmen Geld, wie wiederkehrend sind die Umsätze? | Lagebericht, Item 1 im 10-K |
| Wettbewerbsvorteil | Woran zeigt sich ein Vorteil in den Zahlen (stabile Bruttomarge, hoher ROIC über Zyklen)? | Kennzahlen plus Lagebericht |
| Segmente | Welche Segmente wachsen und tragen den Gewinn? | Segmentberichterstattung |
| Kundenkonzentration | Gibt es Kunden über 10 Prozent des Umsatzes? | Anhang |
| Risikofaktoren | Was ist neu im Vergleich zum Vorjahr? | Risikobericht, Item 1A. Der Agent vergleicht beide Jahre Absatz für Absatz |
| Management und Anreize | Woran ist die Vergütung gekoppelt, wie viel Eigenbesitz besteht? | Vergütungsbericht, Proxy Statement (DEF 14A) |
| Kapitalallokation | Wie wurden Übernahmen der letzten 5 Jahre bewertet, gab es Wertminderungen darauf? | Anhang Goodwill |
| Bilanzpolitik | Wechsel des Abschlussprüfers, geänderte Bilanzierungsmethoden, Geschäfte mit nahestehenden Personen | Anhang, Bestätigungsvermerk |
| Prüfungsschwerpunkte | Was hat der Abschlussprüfer als besonders wichtig hervorgehoben (Key Audit Matters, Critical Audit Matters)? | Bestätigungsvermerk |

### 3.8 Insider-Signal

Die Forschung ist eindeutig in einem Punkt. Nicht jeder Insiderkauf trägt Information. Cohen, Malloy und Pomorski (Journal of Finance 2012) trennen routinemäßige von opportunistischen Insidern. Als routinemäßig gilt, wer in den drei Vorjahren jeweils im selben Kalendermonat gehandelt hat. Mehr als die Hälfte aller Insidergeschäfte war routinemäßig und ohne Vorhersagekraft. Ein Portfolio aus den übrigen, opportunistischen Geschäften erzielte wertgewichtet 82 Basispunkte Überrendite pro Monat. Das ist US-Evidenz aus einem Zeitraum vor der Veröffentlichung und unterliegt dem Abschlag aus Abschnitt 1, Nr. 13.

**Regeln des Insider-Moduls**

1. Nur Käufe am offenen Markt zählen als positives Signal. In US-Daten (Form 4) ist das Transaktionscode P. Zuteilungen (A), Optionsausübungen (M), Steuereinbehalte (F) und Schenkungen (G) werden ignoriert.
2. Verkäufe sind schwache Signale, weil sie oft privat motiviert sind. Gewertet werden nur opportunistische Verkäufe mehrerer Insider innerhalb kurzer Zeit.
3. Geschäfte unter einem vorab festgelegten Handelsplan (US Rule 10b5-1, seit 2023 im Form 4 gekennzeichnet) gelten als routinemäßig.
4. Klassifikation routinemäßig oder opportunistisch je Person nach der Definition oben. Mit weniger als drei Jahren Historie gilt die Person als "unklar" mit halbem Gewicht.
5. Cluster-Kauf, wenn mindestens 3 verschiedene Führungspersonen innerhalb von 60 Tagen kaufen. Cluster wiegen doppelt.
6. Rollengewicht. Vorstandsvorsitz und Finanzvorstand 1,0, übrige Vorstände 0,8, Aufsichtsrat 0,6, eng verbundene Personen 0,5.
7. Größe relativ zum Marktwert der Firma ist wenig aussagekräftig. Relevanter ist die Größe relativ zum bisherigen Eigenbestand der Person, soweit bekannt.
8. Zeitliches Abklingen mit Halbwertszeit 90 Tage.
9. Länderspezifische Meldeschwellen aus `config/insider_thresholds.yaml` (Deutschland 50.000 EUR ab 2026, EU-Standard 20.000 EUR, abweichende nationale Werte pflegen).
10. Das Insider-Signal darf höchstens 15 Prozent des Gesamtwerts ausmachen (`insider_max_weight`). Es kann eine fundamental schwache Aktie nicht in die Kaufliste heben.

### 3.9 Warnsignale (Red Flags)

Jedes Warnsignal hat Schweregrad (info, warnung, stopp) und Belegstelle.

| Warnsignal | Prüfung | Schweregrad |
|---|---|---|
| Going-Concern-Hinweis | Text im Bestätigungsvermerk | stopp |
| Prüferwechsel ohne Ausschreibungsturnus | Vergleich Prüfer Vorjahr | warnung |
| Verspätete Berichtsabgabe | Einreichungsdatum gegen Frist | warnung |
| Beneish über minus 1,78 | Formel | warnung, Eskalation |
| Forderungen wachsen dauerhaft schneller als Umsatz | DSRI über 3 Jahre | warnung |
| Vorräte wachsen dauerhaft schneller als Umsatz | Vorratsreichweite | warnung |
| FCF-Konversion 3 Jahre unter 0,6 | Formel | warnung |
| Verwässerung über 3 Prozent pro Jahr | share_count_change | warnung |
| Hohe Abhängigkeit von Kapitalaktivierung | aktivierte Entwicklungskosten / Umsatz steigt | info |
| Zinsdeckung unter 2 | Formel | stopp |
| Leerverkäufer-Bericht oder Ermittlungen | Nachrichtenlage, nur mit Quelle | Eskalation an Luca |
| Restatement früherer Jahre | Datenqualitätsprüfung 7 | warnung |
| Wesentliche Geschäfte mit nahestehenden Personen | Anhang | info oder warnung |

### 3.10 Portfolio-Passung

Zurückgestellt, siehe Anhang A. Die Korrelation zu anderen Titeln und die Durchschau auf ETFs sind nicht Teil der Bewertung eines Unternehmens.

### 3.11 Sektorabhängige Scorecards

Standardkennzahlen wie EV/EBIT oder Nettoverschuldung zu EBITDA sind bei Banken, Versicherern und Immobiliengesellschaften sinnlos, weil Schulden dort Rohstoff des Geschäfts sind. Damit alle Unternehmen bewertet werden können, hat jede Unternehmensart eine eigene Scorecard mit eigenen Kennzahlen, eigenen Säulengewichten und eigenem Bewertungsverfahren. Die Zuordnung steht in `config/scorecards.yaml` (Regeln auf SIC- und NACE-Codes plus Kennzahlenregeln). Ein Agent darf eine andere Zuordnung vorschlagen, wirksam wird sie erst nach Lucas Bestätigung.

| Scorecard | Zuordnung | Kernkennzahlen | Bewertungsverfahren | Grundlage |
|---|---|---|---|---|
| Standard | alle übrigen operativen Unternehmen | Katalog aus 3.3, Scores aus 3.5 | Reverse-DCF, DCF-Szenarien, EV/EBIT, FCF-Rendite | Nissim und Penman (2001), Penman (Financial Statement Analysis and Security Valuation) |
| Wachstum ohne Gewinn | EBIT in den letzten 2 Jahren negativ und Umsatzwachstum über 15 Prozent | Mohanram G-Score (8 Signale relativ zum Branchenmedian. ROA, operativer Cashflow zu Bilanzsumme, operativer Cashflow größer Ergebnis, geringe Volatilität von Ergebnis und Umsatzwachstum, F&E-, Investitions- und Werbeintensität), Bruttomarge, Liquiditätsreichweite in Monaten, Verwässerung | EV/Umsatz gegen Wachstum, Reverse-DCF auf Umsatzbasis (3.6) | Mohanram (2005, Review of Accounting Studies). Der G-Score wurde für Aktien mit niedrigem Buchwert-Marktwert-Verhältnis entwickelt, nicht speziell für Verlustfirmen. Er dient hier als Hilfsmaß mit Konfidenzabschlag, bis eine eigene Prüfung auf dieser Scorecard vorliegt |
| Banken | SIC 6020 bis 6099, NACE K64.1 | CET1-Quote, Rendite auf materielles Eigenkapital (ROTE), Kosten-Ertrags-Verhältnis, Quote notleidender Kredite, Risikovorsorge zu Krediten, Einlagenanteil an der Refinanzierung | Kurs zu materiellem Buchwert gegen ROTE minus Eigenkapitalkosten (Residualgewinnlogik). Keine EV-Kennzahlen | Calomiris und Nissim (2014, Journal of Financial Intermediation), Damodaran zu Finanzdienstleistern |
| Versicherer | SIC 6300 bis 6411, NACE K65 | Schaden-Kosten-Quote (Combined Ratio) bei Schaden und Unfall, Solvency-II-Quote in der EU bzw. RBC-Quote in den USA, ROE, Reserveabwicklung, Kapitalanlagerendite | Kurs-Buchwert gegen ROE, Dividendenbarwert | Nissim (2010, "Analysis and Valuation of Insurance Companies", Columbia CEASA) |
| Immobilien und REITs | SIC 6798, 6500 bis 6553, NACE L68 | FFO bzw. EPRA-Ergebnis je Aktie, Beleihungsquote (LTV), Zinsdeckung, Restlaufzeit der Schulden, Leerstand | Kurs zu EPRA NTA bzw. NAV, FFO-Rendite. Fair-Value-Gewinne aus IAS 40 bleiben aus dem Ergebnis | EPRA Best Practices Recommendations |
| Versorger und Netze | SIC 4900 bis 4991, NACE D35 | Nettoverschuldung zu EBITDA, regulierte Kapitalbasis, Investitionsquote, Dividendendeckung | EV/EBITDA, Dividendenrendite gegen Deckung | Standard-DCF mit regulierter Rendite |
| Rohstoffe und Zykliker | SIC 1000 bis 1499, 2800 bis 2899, 3310 bis 3399, 3711 bis 3716 und Halbleiter 3674 | Normalisiertes EBIT über 7 bis 10 Jahre, Bilanzstärke im Abschwung | `ev_ebit_normalized` | Zyklusbereinigung wie in 3.4 |
| Holdings und Beteiligungsgesellschaften | Regel, wenn Beteiligungsbuchwerte über 50 Prozent der Bilanzsumme | Summe der Teile, Abschlag auf den Nettoinventarwert | NAV-Abschlag gegen eigene Historie | |

Jede Scorecard hat einen vollständigen Satz an Säulen nach Abschnitt 6.2, damit Noten über Scorecards hinweg dieselbe Bedeutung haben. Verglichen wird trotzdem nur innerhalb einer Scorecard.

Kategorien und Noten sind in Abschnitt 6 definiert.
