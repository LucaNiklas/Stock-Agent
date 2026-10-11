# ADR 0001: Quelle des Aktienuniversums

Status: angenommen (11.10.2026, Entscheidung Luca)

## Kontext

Das System soll Aktien zeigen und bewerten, die bei Trade Republic handelbar sind. Trade Republic veröffentlicht unter https://app.traderepublic.com/browse/stock eine Produktübersicht ohne Login (am 09.10.2026: 11.197 Aktien).

Untersuchung am 11.10.2026:

- Die Seite ist eine Single-Page-App. Die Instrumentenliste kommt nicht als Datei, sondern über `api.traderepublic.com`.
- Vor der Seite liegt der Bot-Schutz AWS WAF: Die Seite lädt dessen `challenge.js` und schickt Telemetrie an dessen Server. Ein Programm käme nur an die Daten, wenn es diesen Schutz umgeht. Das ist ausgeschlossen. Außerdem verbietet die Spezifikation das private App-Protokoll (HR-09).
- Die Tabelle lädt beim Scrollen nach und hat keinen Export. Ein manueller Export von rund 11.000 Zeilen ist nicht praktikabel.
- Die Sitemap von traderepublic.com (robots.txt erlaubt alles) enthält keine Instrumentenseiten.

## Entscheidung

Basis des Universums sind die öffentlichen "All tradable instruments"-Dateien der Deutschen Börse für Börse Frankfurt und Xetra. Übernommen werden nur Stammaktien (Instrument Type `CS`).

- Die Datei-Links enthalten wechselnde Kennungen (zuletzt geändert am 10.11.2025). Deshalb liest das System die Downloadseiten aus `config/sources.yaml` und sucht den Link über den Dateinamen. Findet es nicht genau einen Link, bricht es ab.
- Die LEI kommt aus der öffentlichen ISIN-LEI-Zuordnungsdatei der GLEIF. Gibt es für eine ISIN mehrere LEIs, bleibt sie leer, statt zu raten.
- Ob eine Aktie bei Trade Republic handelbar ist, prüft Luca in der App und hält es mit `stockagent tr-check <ISIN> ja|nein` fest (`state/tr_checks.yaml`). Ohne Eintrag gilt "nicht geprüft".

## Befunde zur Quelle (Stand 12.10.2026)

| Befund | Folge |
|---|---|
| Börse Frankfurt: 14.509 Aktien, Xetra: 1.414. Alle Xetra-Aktien sind auch in Frankfurt gelistet | Frankfurt ist die Basis, Xetra liefert das Merkmal "auch auf Xetra handelbar" |
| Spalte "Country Of Issue" ist bei allen Aktien leer | Anzeige nutzt das Länderkürzel der ISIN, benannt als "Land (ISIN)". Das ist nicht zwingend der Firmensitz |
| Spalte "Currency" ist immer EUR | Handelswährung in Frankfurt, keine Berichtswährung. Nicht angezeigt |
| WKN ist auf neun Stellen mit führenden Nullen aufgefüllt | Wird auf sechs Stellen gekürzt |
| "Primary Market MIC Code" nennt etwa XFRA für Siemens und XMUN für Allianz | Kein verlässlicher Primärmarkt. Angezeigt als "Referenzmarkt", nicht als Kursquelle verwenden |
| ISIN-LEI-Zuordnung trifft 8.373 von 14.509 Aktien (58 Prozent) | Rest bleibt "unbekannt" (HR-05) |
| Viele Unternehmen erscheinen mehrfach (Stammaktie, ADR, CDR, CDI) | Zusammenführung über LEI folgt mit den Abschlussdaten |

## Folgen

- Das Universum ist größer als das von Trade Republic (14.509 gegenüber 11.197). Ein Teil der Aktien ist dort nicht handelbar. Der Status "nicht geprüft" macht das sichtbar.
- Höchstens ein vollständiger Abruf je Woche (`min_refresh_days`). Weicht die Anzahl um mehr als 5 Prozent ab, wird die neue Liste nur mit `--force` übernommen.
- Rohdateien liegen unverändert unter `data/raw/` (SHA-256, gzip). Die GLEIF-Datei ist bereits ein ZIP mit rund 33 MB, das summiert sich bei wöchentlichem Abruf. Eine Aufräumregel für ältere GLEIF-Stände ist noch offen.
- Sollte Trade Republic eine offizielle Liste oder Schnittstelle anbieten, wird sie als zusätzliche Quelle eingebunden und setzt den Status automatisch.
