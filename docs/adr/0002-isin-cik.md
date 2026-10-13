# ADR 0002: Zuordnung ISIN zu CIK der SEC

Status: angenommen (13.10.2026, Entscheidung Luca)

## Kontext

Das Universum kennt jede Aktie über ihre ISIN. Die SEC führt Unternehmen unter ihrer CIK und
liefert weder ISIN noch CUSIP. Das LEI-Feld der Submissions ist meist leer (geprüft bei Apple am
12.10.2026). Die Börsennamen der Deutschen Börse sind abgekürzt („COM.HEALTHC.TR.INC.DL-,01“),
und das Börsenkürzel ist nicht der US-Ticker. Ein reiner Namensvergleich wäre deshalb unsicher.

Geprüfte Wege (12. und 13.10.2026):

| Weg | Ergebnis |
|---|---|
| Namensvergleich Börsenname gegen SEC-Name | unsicher wegen Abkürzungen |
| CUSIP über die EDGAR-Volltextsuche (`efts.sec.gov`) | exakt, aber im Netz dieser Umgebung gesperrt und aufwendig (13G-Deckblätter auswerten) |
| onvista.de | im Netz gesperrt, keine Schnittstelle, nur HTML-Suche, Nutzungsbedingungen nicht geprüft |
| finanzen.net | verbietet automatisierte Abfragen (ADR 0001) |
| **OpenFIGI** (Bloomberg, `api.openfigi.com`) | offizielle, kostenlose Schnittstelle: ISIN -> Ticker je Börse. Ohne Schlüssel 25 Anfragen je Minute mit je 10 ISINs (Antwort-Header `ratelimit-policy: 25;w=60`, mehr als 10 Aufträge ergeben HTTP 413) |

## Entscheidung

Zweistufig mit exakten Nachschlagen statt Namensraten:

1. **OpenFIGI:** ISIN -> Ticker an der US-Sammelbörse (`exchCode` = `US`). Gibt es dort genau
   einen Ticker, gilt er. Schreibweise der Aktiengattung wird an die SEC angepasst (`BRK/B` ->
   `BRK-B`).
2. **Tickerliste der SEC** (`company_tickers_exchange.json`): Ticker -> CIK.
3. **Plausibilität:** Börsenname, LEI-Name oder OpenFIGI-Name muss zum SEC-Namen passen
   (`core/identifiers.names_plausibly_match`). Sonst Status `unsicher`, CIK leer.
4. **Rückfall ohne US-Ticker:** nur, wenn der volle LEI-Name nach Entfernen der Rechtsform genau
   einem SEC-Namen entspricht. Der abgekürzte Börsenname allein reicht nie.
5. **Lucas Zuordnung** in `state/cik_overrides.yaml` (`stockagent sec map <ISIN> <CIK>|keine`)
   hat Vorrang vor allem.
6. Unsicheres bleibt leer, mit Grund in `isin_cik.detail`. Geraten wird nicht.

Jede OpenFIGI-Antwort liegt in `data/raw/`, die angefragten ISINs stehen im Fragment der URL.
Zuordnungen werden nach `openfigi.recheck_days` (90 Tage) neu geprüft, weil Ticker wechseln.

`edgartools` wird nicht genutzt, obwohl SPEC 7.2 es bis Version 4.1 nannte: Für drei
JSON-Adressen und die XBRL-Dateien einer Einreichung reicht die Standardbibliothek plus
`defusedxml`. Der eigene Zwischenspeicher der Bibliothek liefe an `data/raw/` vorbei (SPEC 7.6).

## Folgen

- Ein Ticker, der laut SEC zu einem anderen Namen gehört, bleibt unsicher und erscheint in
  `stockagent sec update` als Zahl. Luca kann ihn mit `sec map` festlegen.
- Hinterlegungsscheine ohne eigene SEC-Berichte (nicht gesponserte ADRs) haben einen US-Ticker,
  aber keinen Eintrag in der Tickerliste: Status `keine`.
- Ausländische Melder mit 20-F (etwa SAP) werden über ihren ADR-Ticker gefunden, wenn die ISIN
  des ADR im Universum steht. Die Zuordnung der Stammaktie folgt mit der Zusammenführung über
  die LEI (offen, STATUS.md).
