## 12. Standardisiertes Analyseformat und Reproduzierbarkeit

### 12.1 Ziel

Jede Analyse ist gleich aufgebaut, nutzt dieselben Formeln in derselben Version, rundet gleich und ist damit über Zeit und Unternehmen hinweg vergleichbar. Dasselbe Unternehmen mit denselben Daten ergibt dieselbe Note.

### 12.2 Formelregister

Alle Formeln stehen in `config/metrics.yaml` und sind in `core/registry.py` implementiert. Jeder Eintrag hat diese Felder.

```yaml
- id: roic
  version: 1.0
  name: "Rendite auf investiertes Kapital"
  formel: "NOPAT / durchschnittliches investiertes Kapital"
  definition: |
    NOPAT = EBIT * (1 - effektiver Steuersatz, begrenzt auf [0; 0,35])
    investiertes Kapital = Eigenkapital + Finanzschulden + Leasingverbindlichkeiten - liquide Mittel
    Durchschnitt = (Anfang + Ende) / 2
  eingaben: [ebit, income_tax, pretax_income, equity, financial_debt, lease_liabilities, cash]
  einheit: ratio
  richtung: higher_better
  rundung: {anzeige: percent, nachkommastellen: 1}
  scorecards: [standard, growth, utilities, cyclicals]
  quelle: "Koller, Goedhart, Wessels. Valuation (McKinsey)"
  tests: [tests/metrics/test_roic.py]
```

Der Hash des Registers steht im Manifest jedes Laufs und im Kopf jeder Analyse. Ändert sich eine Formel, entsteht eine neue Version. Im ersten Lauf danach rechnet das System beide Versionen und zeigt die Abweichung. Ein Anhang "Formelverzeichnis" listet in jeder Analyse alle verwendeten Formeln mit Version.

### 12.3 Feste Gliederung jeder Analyse

Jede Einzelanalyse hat dieselben 14 Abschnitte in derselben Reihenfolge. Ist ein Abschnitt nicht anwendbar, steht dort "nicht anwendbar" mit Grund.

| Nr. | Abschnitt | Inhalt | Erzeugt von |
|---|---|---|---|
| 1 | Kopf | Name, ISIN, LEI, Handelbarkeitsstatus bei Trade Republic mit Quelle, Scorecard, Rechnungslegungsstandard, Berichts- und Kurswährung, Datenstand, Lauf-ID, Methodik-Version, Register-Hash | Python |
| 2 | Urteil | Note · Konfidenz · Risiko, Kategorie, Veränderung zum letzten Lauf | Python |
| 3 | These | höchstens drei Sätze mit Platzhaltern für Zahlen | A9 |
| 4 | Geschäftsmodell und Segmente | Umsatz und Ergebnis je Segment und Region, Kundenkonzentration | Python plus A4 |
| 5 | Kennzahlentabelle | feste Reihenfolge der Kennzahlen, 10 Jahre plus TTM, Branchenmedian, Perzentil | Python |
| 6 | Ertragsqualität und Bilanz | Piotroski, Altman, Beneish, Accruals, FCF-Konversion | Python plus A3 |
| 7 | Bewertung | Reverse-DCF, Szenarien mit Annahmen, Multiples, Football Field, Sensitivität | Python plus A5 |
| 8 | Anpassungen | angewandte Normalisierungen aus 4.3 und Währungsumrechnungen aus 5.2 mit Beträgen | Python |
| 9 | Insider | Transaktionen der letzten 24 Monate, Klassifikation, Signal | Python plus A6 |
| 10 | Qualitative Befunde | Themen aus 3.7 mit Zitat und Seite | A4 |
| 11 | Gegenposition | Bear-Fall, Pre-Mortem, Frühindikatoren, Erwiderung | A7, A3, A5 |
| 12 | Ungereimtheiten | alle gefundenen Fälle aus 12.4 oder "keine gefunden" mit Liste der ausgeführten Prüfungen | Python |
| 13 | Prüfprotokoll | Ergebnisse der Ebenen 0 bis 4, Jury-Werte je Kriterium, entfernte Claims | Python |
| 14 | Grenzen und Quellen | fehlende Daten, Konfidenzgründe, vollständiges Quellenverzeichnis | Python |

Technik. Berichte entstehen ausschließlich aus einem Pydantic-Objekt `AnalysisReport` über Jinja2-Vorlagen (`report/templates/analysis.md.j2` und `analysis.html.j2`). Der Renderer ersetzt die Platzhalter aus HR-01 durch formatierte Werte aus `metrics`. Freitext der Agenten steht nur in den Feldern These, Befunde, Gegenposition und Erklärung, jeweils mit Zeichenobergrenze.

Rundung und Format. Prozentwerte mit einer Nachkommastelle, Multiples mit einer Nachkommastelle, Beträge in Millionen ohne Nachkommastellen, Währung immer angegeben, deutsches Zahlenformat im Bericht. Intern rechnet das System mit `Decimal` für Geldbeträge und `float64` für Verhältnisse und rundet nur bei der Anzeige.

Für die Gesamtübersicht eines Laufs gilt dieselbe Logik mit der Gliederung aus Abschnitt 13.2.

### 12.4 Katalog der Ungereimtheiten

Jede Prüfung läuft bei jeder Analyse. Gefundene Fälle erscheinen in Abschnitt 12 der Analyse mit beiden widersprüchlichen Werten und ihren Quellen.

| ID | Ungereimtheit | Erkennung | Folge |
|---|---|---|---|
| INC-01 | Zwei Quellen nennen verschiedene Werte | Abweichung über 1 Prozent bei Kernwerten | Warnung, über 5 Prozent Eskalation |
| INC-02 | Bilanz geht nicht auf | Aktiva ungleich Passiva über 0,5 Prozent | Kennzahlen dieser Periode `unknown` |
| INC-03 | Segmente ergeben nicht den Konzern | Summe der Segmente plus Überleitung ungleich Konzernwert | Warnung |
| INC-04 | XBRL und PDF widersprechen sich | Abgleich bei extrahierten Werten | Eskalation |
| INC-05 | Bereinigte und unbereinigte Zahlen driften auseinander | Abstand über 20 Prozent in drei Jahren | Warnung im Bericht, Ertragsqualität sinkt |
| INC-06 | Gewinn ohne Cash | operativer Cashflow unter 60 Prozent des Ergebnisses in drei Jahren | Warnung |
| INC-07 | Aktienanzahl passt nicht zur Marktkapitalisierung | Bilanzangabe gegen Marktdaten über 3 Prozent | Datenprüfung, Eskalation |
| INC-08 | Währung oder Einheit unklar | fehlende oder widersprüchliche Angabe | Wert `unknown` |
| INC-09 | Periode verschoben | abweichender Stichtag zwischen Quellen | Neuzuordnung, Warnung |
| INC-10 | Prüfer uneinig | Jury-Spannweite über 2 Punkte | Eskalation |
| INC-11 | Aussage des Managements widerspricht den Zahlen | A4 findet eine Aussage, J1 die gegenteilige Kennzahlentwicklung | Warnung mit Zitat und Kennzahl |
| INC-12 | Restatement | spätere Fassung ändert Vorjahreswerte | Warnung, beide Fassungen im Bericht |
| INC-13 | Wechselkurs unplausibel | abgeleiteter Kurs weicht über 2 Prozent vom Referenzkurs ab | Daten- oder Einheitenfehler, Eskalation |
| INC-14 | Agent wollte eine Zahl ohne Platzhalter schreiben oder ein nicht wörtliches Zitat verwenden | Zahlen- und Zitat-Gate | Claim entfernt, Vorfall gezählt |

### 12.5 Reproduzierbarkeit

Der deterministische Teil (Daten, Kennzahlen, Scores, Note, Bewertungsrechnung) liefert bei gleichem Datenstand bitgleiche Ergebnisse. Ein Test lädt einen gespeicherten Datenstand, rechnet zweimal und vergleicht die Ausgaben byteweise.

Sprachmodelle sind nicht deterministisch, auch nicht bei Temperatur null. Atil et al. (2024, "LLM Stability") messen schwankende Antworten bei identischen Eingaben, und Thinking Machines Lab (He, 2025, "Defeating Nondeterminism in LLM Inference") führt das unter anderem auf die Zusammenstellung der Anfragen beim Anbieter zurück. Das System begegnet dem auf vier Wegen.

1. Zwischenspeicher. Jede Agentenausgabe wird unter dem Hash aus Prompt-Version, Eingaben und Modellklasse gespeichert. Ändern sich die Eingaben nicht, wird die gespeicherte Ausgabe wiederverwendet. Gleiche Daten ergeben damit denselben Text.
2. Mehrfachbewertung. Einordnungen wie positiv, neutral oder negativ und die Jury-Werte werden dreimal erzeugt. Es gilt die Mehrheit bzw. der Median, die Streuung wird protokolliert (Self-Consistency nach Wang et al. 2023, ICLR).
3. Begrenzter Einfluss. Note und Kategorie sind deterministische Funktionen der Kennzahlen (HR-13). DCF-Annahmen des Bewertungsagenten sind durch Regeln begrenzt (3.6), deshalb kann eine abweichende Formulierung die Kategorie nicht ändern.
4. Aufgezeichnete Antworten. Tests nutzen gespeicherte Modellantworten zu festen Testdaten. Damit sind auch die Berichte im Test bitgleich (Snapshot-Tests).

### 12.6 Reihenfolge der Schranken

Jede Agentenausgabe durchläuft dieselben Schranken in dieser Reihenfolge, bevor ein Prüfer sie sieht.

1. Schema-Gate (Pydantic-Validierung)
2. Zahlen-Gate (HR-01)
3. Beleg-Gate (HR-02)
4. Zitat-Gate (HR-03)
5. Formulierungs-Gate (HR-15)
6. Konsistenz-Gate. Jede eingesetzte Zahl im fertigen Bericht stimmt mit `decision.json` und `metrics` überein

Abgelehnte Ausgaben gehen mit der Fehlermeldung bis zu zweimal zurück an den Agenten. Danach wird der Fall eskaliert.
