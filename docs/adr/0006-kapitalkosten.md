# ADR 0006: Kapitalkosten und Reverse-DCF

Status: angenommen (19.10.2026, Entscheidung Luca)

## Kontext

SPEC 3.6 verlangt Kapitalkosten aus risikofreiem Zins, Aktienrisikoprämie nach Damodaran,
Branchenbeta nach Damodaran (um die eigene Verschuldung bereinigt) und Fremdkapitalkosten nach
Steuern. Darauf baut der Reverse-DCF als Hauptverfahren der Bewertung. Offen waren Steuersatz,
Zuordnung der Firmen zu Damodarans Branchen und der Umgang mit Firmen außerhalb der USA.

Geprüfte Quellen (19.10.2026, alle ohne Schlüssel erreichbar):

| Quelle | Inhalt | Format |
|---|---|---|
| Bundesbank, `api.statistiken.bundesbank.de` | Zinsstrukturkurve börsennotierter Bundeswertpapiere, 10 Jahre, täglich | CSV |
| US-Finanzministerium, `home.treasury.gov` | Daily Treasury Par Yield Curve, 10 Jahre, je Jahr eine Datei | CSV |
| Damodaran, `pages.stern.nyu.edu` | Branchenbetas USA, Rating nach Zinsdeckung, Kapitalkosten je Branche (Stand Januar), implizite Risikoprämie je Monat, Branchenzuordnung von rund 48.000 Firmen weltweit | HTML, Excel |

## Entscheidung

1. **Risikofreier Zins:** 10-jährige Bundesanleihe für Berichtswährung EUR, 10-jährige Treasury
   für USD, am letzten Handelstag bis zum Stichtag (höchstens 7 Tage alt). Andere
   Berichtswährungen haben vorerst keinen WACC (Umrechnung über die Inflationsdifferenz nach
   SPEC 5.2 Nr. 6 offen).
2. **Risikoprämie:** Damodarans implizite Prämie „ERP (T12m)“ des Monats.
3. **Beta:** Damodarans unverschuldetes Branchenbeta, um Kasse bereinigt, mit der eigenen
   Verschuldung neu verschuldet: beta_u * (1 + (1 - Steuersatz) * FK / EK), EK = Börsenwert,
   FK = Finanzschulden + Leasing. Bis Schritt 7 gelten die US-Betas für alle Firmen (Vermerk
   `BETA_USA`, Lucas Entscheidung). Damodarans Europa-Tabelle gibt es nur als Excel.
4. **Branche bei Damodaran** (Lucas Entscheidung): über Börse und Kürzel aus Damodarans
   Firmenliste (Yahoo-Symbol oder Tickerliste der SEC), sonst die häufigste Branche unter
   Damodarans Firmen mit demselben SIC-Code. Luca kann je ISIN festlegen
   (`stockagent markt branche <ISIN> <Branche>`, `state/damodaran_branchen.yaml`).
5. **Steuersatz** (Lucas Entscheidung): gesetzlicher Satz je Land in `config/kapitalkosten.yaml`,
   USA 21 %, Deutschland 29,83 %. Der tatsächlich gezahlte Satz schwankt zu stark.
6. **Fremdkapitalkosten:** risikofreier Zins plus Aufschlag aus dem synthetischen Rating nach
   Zinsdeckung (Damodarans Tabelle für große Firmen, Finanzfirmen mit eigener Tabelle). Meldet
   die Firma keinen Zinsaufwand (Apple seit 2023), gilt der Aufschlag ihrer Branche:
   Fremdkapitalkosten der Branche laut Damodaran minus Damodarans Treasury-Zins zum Stand der
   Tabelle (Vermerk `KD_BRANCHE`).
7. **Reverse-DCF:** FCFF = FCF + Zinsaufwand * (1 - Steuersatz), 10 Jahre konstantes Wachstum,
   danach Endwert nach Gordon mit Endwachstum min(risikofreier Zins, 2,5 %). Gesucht wird das
   Wachstum per Intervallhalbierung zwischen -50 % und +100 %, danach die Rückrechnung Jahr für
   Jahr im Rechenweg (CP-06, Toleranz 0,1 %). Ist der FCFF nicht positiv: Umsatz mal Zielmarge,
   Zielmarge vorerst der Median der eigenen FCF-Margen (Branchenmedian mit der Vergleichsgruppe
   aus Schritt 5).
8. **Stand der Damodaran-Daten:** Betas, Ratings und Branchenzuordnung gibt es nur als
   aktuellen Stand (jährlich im Januar). Für frühere Geschäftsjahre gilt derselbe Stand
   (Vermerk `BETA_STAND`). Die Risikoprämie liegt monatlich ab 2008 vor.

## Folgen

- Neue Befehle `stockagent markt update | show | branche`, Tabellen `rates` und `damodaran_*`
  (Schema 8).
- Vier neue Kennzahlen: `wacc`, `implied_growth`, `ev_ebit_normalized`, `altman_z`.
- Banken bekommen keinen WACC (keine Finanzschulden im Sinne der Brücke), eigene Bewertung in
  Schritt 8.
- Die Damodaran-Daten beziehen sich auf US-Firmen. Für europäische Firmen ist das eine
  Näherung, bis Schritt 7 die Europa-Betas lädt.
