# ADR 0012: Insider-Signal aus SEC Form 4 (Bauschritt 9)

Status: angenommen (21.10.2026, Lucas Auftrag „fahre fort mit den nächsten zwei Bauschritten“).

## Kontext

SPEC 3.8 verlangt ein Insider-Signal mit zehn Regeln, SPEC 7.3 als Quellen SEC Form 4 (USA) und
die BaFin-Datenbank (Deutschland), SPEC 8.3 den Agenten A6, SPEC 12.3 Abschnitt 9 im Bericht.

## Entscheidung

1. **Quelle USA:** Form 4 je Meldung als XML aus EDGAR (`data/sources/form4.py`), Auswahl über
   die Einreichungsliste (Submissions) der letzten 5 Jahre, höchstens 400 Meldungen. Gelesene
   Meldungen merkt sich `insider_filings` (Schema 12), sie werden nicht erneut geladen.
2. **Was zählt:** nur Geschäfte am offenen Markt (Code P und S). Einordnung je Person nach
   Cohen, Malloy und Pomorski (2012): routinemäßig, opportunistisch oder unklar (weniger als drei
   Jahre Historie, halbes Gewicht). Handelsplan nach Rule 10b5-1 (Feld `aff10b5One`) =
   routinemäßig. Cluster ab 3 Personen in 60 Tagen doppelt. Verkäufe nur, wenn mindestens 3
   Personen in 60 Tagen opportunistisch verkaufen. Rollengewicht, Größe relativ zum Eigenbestand,
   Abklingen mit 90 Tagen Halbwertszeit. Alles in `config/insider_thresholds.yaml`.
3. **Säule Insider als fester Wert** (0 bis 100, 50 = kein Signal), nicht als Rang in der
   Vergleichsgruppe. Grund: Ein Rang bräuchte Form 4 aller 50 Vergleichsfirmen (Tausende
   Abrufe), und das Signal ist absolut gemeint (ein opportunistischer Kauf ist ein Kauf, egal was
   die Gruppe tut). Ohne Geschäft am offenen Markt fehlt die Säule, zählt nicht zur Abdeckung und
   ihr Gewicht geht auf die anderen Säulen (SPEC 6.2). Gewicht 10 %, höchstens 15 % als
   Prüfpunkt CP-07 (SPEC 3.8 Nr. 10).
4. **Belege für A6:** Jede Meldung wird zusätzlich als Dokument mit lesbarer Textseite
   gespeichert (`doc_type` FORM4). A6 zitiert wörtlich daraus, Zitat-Gate und J2 prüfen wie bei
   Jahresberichten. A6 ordnet ein (Kauf nach Kursrückgang, mehrere Käufer, Handelsplan) und ändert
   weder Säule noch Note (HR-13). A6 läuft nur, wenn es Geschäfte am offenen Markt in den letzten
   24 Monaten gibt, A7 wartet dann auf A6.
5. **Anzeige:** Dashboard mit Filter Insider (Käufe, Verkäufe, kein Signal) und Zeitachse der
   Geschäfte auf der Unternehmensseite, Abschnitt 9 des Berichts, `stockagent insider update` und
   `show`.

## Geprüft

Handrechnung mit echten Meldungen: Intel, Finanzvorstand David Zinsner, Kauf am 26.01.2026, und
CEO Lip-Bu Tan, Kauf über einen Familientrust am 11.08.2026. Säule zum 20.10.2026 = 55,716,
unabhängig mit `math` nachgerechnet (`tests/test_insider.py`). Apple, Ben Borders, 15.10.2026:
Verkäufe unter Handelsplan, korrekt als routinemäßig ohne Signal.

## Abweichungen und offen

- *Abweichung:* BaFin fehlt. `portal.mvp.bafin.de` ist in dieser Umgebung gesperrt (Proxy 403).
  Ohne echte Antwort wird kein Leser gebaut (nichts raten). Domain-Freigabe ist eine Frage an
  Luca. Die Meldeschwellen für DE und EU stehen schon in der Konfiguration.
- Handelspläne vor April 2023 sind nur in Fußnoten vermerkt und werden nicht erkannt.
- Bei gemeinsamen Meldungen mehrerer Personen gilt die erste meldende Person.
- Die Submissions der SEC führen die letzten 1000 Einreichungen. Für sehr aktive Melder kann die
  Historie für die Einordnung kürzer sein (dann „unklar“ mit halbem Gewicht).
