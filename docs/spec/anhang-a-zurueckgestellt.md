## Anhang A. Zurückgestellte Module aus Version 3

Diese Teile werden nicht gebaut, solange Luca sie nicht ausdrücklich freigibt (19 Nr. 7). Sie stehen hier, damit die Recherche nicht verloren geht. Verweise in diesem Anhang beziehen sich auf die Nummerierung von Version 3.

### A.1 Ausgangslage Portfolio (Version 3, Abschnitt 2.1 und 2.2)

#### 2.1 Bestände (Stand 08.10.2026, von Luca angegeben)

| Position | Betrag in EUR | Anteil am Gesamtvermögen |
|---|---|---|
| ETFs bei Trade Republic | 7.900 | 11,7 % |
| ETFs und Fonds bei Baader (MSCI-World-nah) | 55.000 | 81,2 % |
| Einzelaktien bei Trade Republic | 2.400 | 3,5 % |
| Anleihen | 400 | 0,6 % |
| Krypto | 470 | 0,7 % |
| Summe | 67.770 | 100 % |

ETFs und Fonds machen zusammen 62.900 EUR aus, also 92,8 Prozent.

#### 2.2 Die Zielallokation ist eine große Entscheidung

Bezieht sich das Ziel "60 bis 70 Prozent ETFs, Rest Einzelaktien" auf das Gesamtvermögen, müssten Einzelaktien 30 bis 40 Prozent ausmachen. Das wären heute 20.300 bis 27.100 EUR statt 2.400 EUR, also das Acht- bis Elffache. Wer dafür ETF-Anteile verkauft, realisiert Kursgewinne und zahlt Abgeltungsteuer. Der naheliegende Weg ist, den Einzelaktienanteil über neue Sparraten aufzubauen.

Bezieht sich das Ziel nur auf das Trade-Republic-Depot (12.770 EUR), ist der Einzelaktienanteil mit 19 Prozent schon nahe am Ziel.

Das System behandelt beides als Konfiguration. In `config/portfolio.yaml` stehen `allocation_scope` (`total` oder `trade_republic`), `target_etf_share_min` und `target_etf_share_max`. Der Default ist `total` mit 0,60 und 0,70, damit die Rechnung sichtbar wird. Luca entscheidet (Abschnitt 19).

### A.2 Portfolio-Passung (Version 3, Abschnitt 3.10)

1. Durchschau-Gewichte. Für jeden ETF und Fonds im Bestand werden die Positionsdateien der Emittenten geladen (zum Beispiel iShares-CSV). Daraus entsteht das bestehende Gewicht jeder Aktie im Gesamtvermögen.
2. Diversifikationsbeitrag. Für jeden Kandidaten rechnet das System, wie sich Länder-, Branchen- und Währungsgewichte und das Gewicht der zehn größten Einzelrisiken verändern, wenn die vorgeschlagene Position dazukommt.
3. Lücken im ETF-Bestand. Ein MSCI-World-Portfolio enthält keine Schwellenländer und keine Small Caps. Ob Einzeltitel diese Lücken gezielt füllen sollen, ist eine Entscheidung von Luca (`fill_gaps_preference`, Default `neutral`).
4. Korrelation. Tägliche Renditen der letzten 3 Jahre gegen bestehende Einzeltitel. Neue Kandidaten mit Korrelation über 0,8 zu einer bestehenden Position bekommen einen Abschlag.
5. Positionsgrößen. Gleichgewichtung als Ausgangspunkt, angepasst um Überzeugungsstufe (A, B, C mit Faktoren 1,25 / 1,0 / 0,75). Höchstgewicht je Einzeltitel nach Risikoklasse (6.4), gemessen am Gesamtvermögen einschließlich Durchschau-Gewicht (`max_position_total`). Dazu die Liquiditätsgrenze je Order aus 3.1. Höchstgewicht je Branche im Einzeltitelteil 25 Prozent. Mindestens 10 Einzeltitel, bevor der Einzeltitelanteil 15 Prozent des Gesamtvermögens überschreitet.
6. Kein Kelly-Kriterium und keine Mittelwert-Varianz-Optimierung in v1. Beide reagieren extrem auf Schätzfehler in den erwarteten Renditen.
7. Steuern als Information. Bei Verkaufsprüfungen zeigt das System den realisierten Gewinn, den Sparerpauschbetrag als Konfigurationswert und den Hinweis auf Quellensteuer bei ausländischen Dividenden. Für Aktienverluste existiert in Deutschland ein eigener Verlustverrechnungstopf. Steuerregeln werden vor jeder Verkaufsempfehlung als "bitte aktuell prüfen" markiert, weil das System keine Steuerberatung leistet.

### A.3 Import der Bestände (Version 3, Abschnitt 9.6)

- Trade Republic. CSV-Export der Transaktionen aus der App oder über `pytr export_transactions` (optional). Die Zugangsdaten bleiben ausschließlich auf Lucas Rechner, nie in der Cloud.
- Baader-Depot. CSV oder manuell gepflegte `data/holdings_manual.yaml` mit ISIN und Stückzahl.
- Nach jedem Import zeigt das System Abweichungen zum vorigen Stand zur Bestätigung.

### A.4 Bestandsprüfung und Verkaufslogik (Version 3, Abschnitt 10)

#### 10.1 Grundsatz

Jeder Titel in Lucas Depot wird in jedem Lauf vollständig geprüft, unabhängig von der gewählten Kategorie. Die Verkaufslogik folgt drei Befunden der Verhaltensforschung.

| Befund | Quelle | Folgerung |
|---|---|---|
| Anleger verkaufen Gewinner zu früh und halten Verlierer zu lange (Dispositionseffekt) | Shefrin und Statman (1985, Journal of Finance) | Kaufkurs spielt für das Verkaufsurteil keine Rolle, nur für die Steuer |
| Privatanleger verkaufen eher Gewinner. Die verkauften Gewinner entwickeln sich danach besser als die gehaltenen Verlierer | Odean (1998, Journal of Finance) | Kursgewinn allein ist kein Verkaufsgrund |
| Die aktivsten Privatanleger erzielen nach Kosten die schlechtesten Renditen | Barber und Odean (2000, Journal of Finance) | Hohe Hürde für Verkäufe und Tausch |
| Der Vermögenszuwachs des Marktes stammt von wenigen außergewöhnlichen Gewinnern | Bessembinder (2018) | Gewinner mit intakter These laufen lassen |
| Stop-Loss-Regeln helfen nur, wenn Renditen Trendverhalten zeigen, und kosten sonst Rendite | Kaminski und Lo (2014, Journal of Financial Markets) | Keine prozentualen Stop-Loss-Regeln |

#### 10.2 Thesenkarte

Für jede Position gibt es eine Thesenkarte in `state/theses/<isin>.yaml`. Bei einem neuen Kauf entwirft der Synthese-Agent sie, Luca bestätigt sie. Für bestehende Positionen erstellt `/depot-check --onboard` beim ersten Lauf Entwürfe, die Luca bestätigt oder ändert.

```yaml
isin: DE000XXXXXXX
erstellt: 2026-10-22
methodology_version: 3.0
these: "Bis zu drei Sätze. Warum dieses Unternehmen über 5 bis 10 Jahre Wert schafft."
kernkennzahlen:
  - metric: roic
    erwartung: ">= 0.15"
    pruefung: jahresbericht
  - metric: revenue_cagr_3y
    erwartung: ">= 0.05"
    pruefung: jahresbericht
kill_kriterien:
  - "Bruttomarge fällt zwei Jahre in Folge um mehr als 3 Prozentpunkte"
  - "Nettoverschuldung über dem 3-fachen EBITDA"
erwartete_note: "B oder besser"
zielgewicht_gesamtvermoegen: 0.02
naechste_ueberpruefung: 2027-04-30
```

Kill-Kriterien sind maschinenprüfbar formuliert. Textliche Kriterien übersetzt Claude Code beim Anlegen in Regeln über Kennzahl-IDs und zeigt die Übersetzung zur Bestätigung.

#### 10.3 Prüfungen je Lauf

Die Prüfungen sind deterministisch (`core/holdings_review.py`). Der Bestandsprüfer A10 erklärt die Ergebnisse, prüft qualitative Thesenpunkte gegen neue Berichte und kann wie alle Agenten nur abwerten oder eskalieren (HR-13).

| ID | Prüfung | Auslöser | Ergebnis |
|---|---|---|---|
| HOLD-01 | These intakt | Eine Kernkennzahl liegt in zwei aufeinanderfolgenden Berichtsperioden außerhalb ihrer Erwartung | Halten und beobachten, bei zwei Kernkennzahlen Verkauf prüfen |
| HOLD-02 | Kill-Kriterium | ein Kriterium erfüllt | Verkauf prüfen |
| HOLD-03 | Note | D oder E in zwei aufeinanderfolgenden Läufen | Verkauf prüfen |
| HOLD-04 | Stopp-Flag | Going Concern, Zinsdeckung unter 2, Restatement mit Hinweis auf Bilanzmanipulation | Verkauf prüfen, sofortige Eskalation |
| HOLD-05 | Bewertung extrem | Bewertungssäule unter dem 10. Perzentil und implizites Wachstum über dem 90. Perzentil der eigenen 10-Jahres-Historie | Teilverkauf prüfen, nur wenn die Position über ihrem Zielgewicht liegt |
| HOLD-06 | Konzentration | Gewicht einschließlich Durchschau über dem 1,5-fachen der Obergrenze aus 6.4 | Teilverkauf auf Zielgewicht prüfen |
| HOLD-07 | Insider | opportunistisches Verkaufscluster nach 3.8 | Halten und beobachten |
| HOLD-08 | Bessere Alternative | Unternehmen derselben Scorecard mit mindestens 15 Punkten höherem Gesamtwert, gleicher oder besserer Konfidenz, als Kaufkandidat verifiziert | Tausch prüfen, mit Steuer- und Kostenrechnung |
| HOLD-09 | Ereignis | Übernahmeangebot, Abspaltung, Delisting | Information und Eskalation |
| HOLD-10 | Datenlage | Konfidenz fällt auf K4 | Halten und beobachten mit Hinweis |

#### 10.4 Steuer- und Kostenrechnung

Bei jedem Ergebnis außer "Halten" rechnet das System. Realisierter Gewinn oder Verlust je Steuerlos (FIFO, wie in Deutschland vorgeschrieben), Abgeltungsteuer von 25 Prozent plus Solidaritätszuschlag von 5,5 Prozent darauf, optional Kirchensteuer (`church_tax_rate` in `config/tax.yaml`), verbleibender Sparerpauschbetrag (Default 1.000 EUR, jährlich zu prüfen), Verrechnung im Aktienverlusttopf und Orderkosten. Beim Tausch rechnet es zusätzlich die Mehrrendite, die der Ersatz pro Jahr bringen müsste, um die Steuerzahlung über 5 Jahre auszugleichen. Jede Steuerangabe trägt den Hinweis, dass das System keine Steuerberatung leistet und die Regeln vor einer Entscheidung aktuell zu prüfen sind.

#### 10.5 Ergebnisstufen

| Stufe | Bedeutung |
|---|---|
| Halten | These intakt, keine Auffälligkeit |
| Halten und beobachten | einzelne Abweichung, benannte Frühindikatoren |
| Teilverkauf prüfen | Gewicht zu hoch oder Bewertung extrem, These intakt |
| Verkauf prüfen | These verletzt, Kill-Kriterium oder Stopp-Flag |
| Tausch prüfen | deutlich bessere Alternative nach Steuern und Kosten |

Jedes Ergebnis enthält Begründung mit Belegen, die Steuerrechnung und die Frage "Was müsste passieren, damit sich die Einschätzung umkehrt?". Das System formuliert nie "verkaufen", sondern "prüfen". Die Entscheidung trifft Luca.

#### 10.6 Ausdrücklich keine Verkaufsgründe

- Kursverlust seit dem Kauf allein
- Kursgewinn seit dem Kauf allein
- prozentuale Stop-Loss-Marken
- Nachrichten ohne erkennbare Wirkung auf Kennzahlen oder These
- ein schwacher Einzelquartalswert ohne Bestätigung im Folgequartal

**Korrekturen aus der Prüfung von Version 3 (vor einem Bau einarbeiten)**

- Beim Verkauf von Fondsanteilen und ETFs gilt die Teilfreistellung nach InvStG (Aktienfonds 30 Prozent, Mischfonds 15 Prozent des Gewinns steuerfrei). Ohne sie ist jede Steuerrechnung für ein Umschichten aus ETFs falsch.
- Bereits versteuerte Vorabpauschalen mindern den steuerpflichtigen Veräußerungsgewinn und müssen je Fondsanteil gespeichert werden.
- Steuerregeln und Freibeträge sind jährlich zu prüfen und stehen nur in `config/tax.yaml`.

### A.5 Agenten A8 und A10 (Version 3, Abschnitt 8.3)

**A8 Portfolio-Agent**
- Rolle. Ergebnisse des Python-Portfoliomoduls (Abschnitt 3.10) erklären und Gewichtungsvorschlag formulieren.
- Ausgabe. `portfolio_proposal` mit Gewicht, Betrag in EUR, Sparplan-Variante, Begründung, Effekt auf Länder, Branchen, Währung und Top-10-Risiken.
- Modell. `standard`.

**A9 Synthese-Agent**
- Rolle. Entscheidungsvorlage schreiben (Abschnitt 13.2).
- Grenzen. Nur geprüfte Inhalte (Status `verified`). Keine neuen Behauptungen.
- Modell. `strong`.

**A10 Bestandsprüfer**
- Rolle. Ergebnisse der Prüfregeln HOLD-01 bis HOLD-10 erklären, qualitative Thesenpunkte gegen neue Berichte prüfen, Thesenkarten für neue Käufe entwerfen.
- Eingabe. Thesenkarte, aktuelle Analyse, Ergebnisse aus `core/holdings_review.py`, Steuerrechnung.
- Ausgabe. `holding_review` je Position mit Ergebnisstufe aus 10.5, Begründung, Belegen und Umkehrbedingung.
- Modell. `strong`.
- Grenzen. Kann nur abwerten oder eskalieren (HR-13). Formuliert nie eine Handlungsanweisung.

### A.6 Schutz der Depotdaten (Version 3, Abschnitt 16.13)

Bestände liegen lokal in `state/holdings.yaml` und werden nie im Klartext committet. Laufen Hauptläufe in GitHub Actions, wird die Datei mit `age` verschlüsselt (`state/holdings.yaml.age`) und im Workflow mit dem Secret `HOLDINGS_AGE_KEY` entschlüsselt. Zugangsdaten für Trade Republic verlassen Lucas Rechner nie.
