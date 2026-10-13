# Testdaten SEC und OpenFIGI (Bauschritt 2)

Gekürzte echte Antworten, damit die Tests ohne Internet laufen. Quelle und Abrufdatum stehen in
jeder Datei (`_quelle` in JSON, Kommentar in XML). Gekürzt wurde nur durch Weglassen, kein Wert
ist verändert.

| Datei | Quelle | Gekürzt auf |
|---|---|---|
| `companyfacts_<CIK>.json` | data.sec.gov Company Facts (Apple, PagerDuty, JPMorgan) | Konzepte aus `config/concept_map.yaml` |
| `submissions_<CIK>.json` | data.sec.gov Submissions | Einreichungen der gekürzten Company Facts aus der Liste `recent` |
| `company_tickers_exchange.json` | www.sec.gov Tickerliste | 7 Zeilen |
| `openfigi_mapping.json` | api.openfigi.com Antwort auf 4 ISINs (die letzte absichtlich ungültig) | US-Einträge und je zwei weitere Börsen |
| `aapl-20250927_htm.xml` | XBRL-Instanz des Apple-10-K vom 31.10.2025 | Werte der Bilanz und GuV ohne Dimensionen, ein Wert mit Dimension |
| `aapl-20250927_cal.xml` | Berechnungsstruktur desselben 10-K | Rollen Bilanz und GuV |
| `aapl_10k_index.json` | Verzeichnis der Einreichung 0000320193-25-000079 | ungekürzt |

Die Handprüfung gegen die 10-K-Dokumente (Seitenangaben) steht in `tests/test_sec_abnahme.py`.
