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
- Land: Zu jeder LEI lädt das System über die GLEIF-API (bis 200 LEIs je Abfrage) rechtlichen Namen, weitere Namen (Sprachvarianten, Umschriften, frühere Namen), Rechtsordnung und Hauptsitz. Gezeigt werden zwei Länder: **Hauptsitz** (`headquartersAddress.country`) und **Rechtssitz** (`jurisdiction`, etwa US-DE -> US). Das Feld `legalAddress` taugt nicht als Rechtssitz: niederländische N.V.s wie Iveco oder Brembo haben dort eine italienische Adresse.
- Plausibilität: Die GLEIF-Zuordnung ISIN -> LEI enthält Fehler. Ein GLEIF-Land wird nur genutzt, wenn der Börsenname zu einem der LEI-Namen passt (`core/identifiers.names_plausibly_match`) und bei normalen Aktien das ISIN-Land zum Rechtssitz passt. Sonst gilt "nur ISIN (unsicher)" oder "widersprüchlich".
- Hinterlegungsscheine (ADR, GDR, CDR, CDI, SDR, NY-Registered Shares) werden am Börsennamen erkannt (`is_depositary_receipt`) und als Art "Hinterlegungsschein" gekennzeichnet. Bei ihnen sagt das ISIN-Land nichts über das Unternehmen.
- Ob eine Aktie bei Trade Republic handelbar ist, prüft Luca in der App und hält es mit `stockagent tr-check <ISIN> ja|nein` fest (`state/tr_checks.yaml`). Ohne Eintrag gilt "nicht geprüft".

## Befunde zur Quelle (Stand 12.10.2026)

| Befund | Folge |
|---|---|
| Börse Frankfurt: 14.509 Aktien, Xetra: 1.414. Alle Xetra-Aktien sind auch in Frankfurt gelistet | Frankfurt ist die Basis, Xetra liefert das Merkmal "auch auf Xetra handelbar" |
| Spalte "Country Of Issue" ist bei allen Aktien leer | Länder kommen aus der GLEIF (siehe Entscheidung), ersatzweise aus dem Länderkürzel der ISIN, dann als unsicher markiert |
| Spalte "Currency" ist immer EUR | Handelswährung in Frankfurt, keine Berichtswährung. Nicht angezeigt |
| WKN ist auf neun Stellen mit führenden Nullen aufgefüllt | Wird auf sechs Stellen gekürzt |
| "Primary Market MIC Code" nennt etwa XFRA für Siemens und XMUN für Allianz | Kein verlässlicher Primärmarkt. Angezeigt als "Referenzmarkt", nicht als Kursquelle verwenden |
| ISIN-LEI-Zuordnung trifft 8.373 von 14.509 Aktien (58 Prozent) | Rest bleibt "unbekannt" (HR-05) |
| Davon passt bei 232 der Börsenname zu keinem LEI-Namen (meist Umbenennungen, einige echte Fehlzuordnungen wie Codexis -> Cedexis) | Land aus der ISIN, als unsicher markiert |
| 39 normale Aktien mit LEI haben ein ISIN-Land, das nicht zum Rechtssitz passt (Steris: irische ISIN, LEI der alten britischen Gesellschaft; Atlassian, Everest, Liberty Global auf Vorgänger- oder Tochtergesellschaften; aber auch korrekte Fälle wie Eurofins mit FR-ISIN und Sitz LU) | als "widersprüchlich" markiert, beide Werte sichtbar |
| Ergebnis 12.10.2026: Hauptsitz laut GLEIF bei 8.102 Aktien, 39 widersprüchlich, 6.368 nur ISIN-Land. 1.540 Hinterlegungsscheine | |
| Viele Unternehmen erscheinen mehrfach (Stammaktie, ADR, CDR, CDI) | Zusammenführung über LEI folgt mit den Abschlussdaten |

## Folgen

- Das Universum ist größer als das von Trade Republic (14.509 gegenüber 11.197). Ein Teil der Aktien ist dort nicht handelbar. Der Status "nicht geprüft" macht das sichtbar.
- Höchstens ein vollständiger Abruf je Woche (`min_refresh_days`). Weicht die Anzahl um mehr als 5 Prozent ab, wird die neue Liste nur mit `--force` übernommen.
- Rohdateien liegen unverändert unter `data/raw/` (SHA-256, gzip). Aufräumregel: GLEIF-Rohdaten (Zuordnungsdatei rund 33 MB und API-Antworten) werden nur für die letzten `gleif.keep_snapshots` (Default 2) übernommenen Stände behalten, ältere löscht `universe update` automatisch. Begründung: Sie enthalten keine Finanzwerte und sind jederzeit neu abrufbar. Listen der Deutschen Börse und alle späteren Berichte werden nie gelöscht (SPEC 7.6).
- Sollte Trade Republic eine offizielle Liste oder Schnittstelle anbieten, wird sie als zusätzliche Quelle eingebunden und setzt den Status automatisch.

## Gegenprüfung mit finanzen.net (11.10.2026)

finanzen.net verbietet in den Nutzungsbedingungen jede automatisierte Abfrage ohne Genehmigung und ist deshalb keine Datenquelle. Als einmalige Stichprobe wurden einzelne Seiten von Hand verglichen, nichts davon wird gespeichert. Befund: finanzen.net nutzt "Land" uneinheitlich, mal Rechtssitz (Xiaomi: Kaiman Islands, Yum China: USA), mal Hauptsitz (Iveco: Italien, Experian: Irland). Jeder geprüfte Wert stimmte mit einer der beiden Spalten Hauptsitz oder Rechtssitz überein. Deshalb zeigt das System beide getrennt.

## Branche

Branche und Kernprodukt sind in Schritt 1 noch nicht enthalten. Quellen nach SPEC 7.8: SIC-Code der SEC für US-Emittenten und SEC-Melder (Schritt 2), danach Wikidata und Lucas Bestätigung.
