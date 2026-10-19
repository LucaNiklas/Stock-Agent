# tests/fixtures/

Kleine Beispieldaten für Tests, damit sie ohne Internet laufen.

- `sec/`: gekürzte echte Antworten von SEC und OpenFIGI für Apple, PagerDuty und JPMorgan
  (Bauschritt 2). Quelle und Abrufdatum stehen in jeder Datei, Übersicht in `sec/README.md`.
- Die Beispieldateien der Deutschen Börse und der GLEIF (Bauschritt 1) erzeugt
  `tests/universe_fixtures.py` im Format der echten Quellen.
- `zinsen/`: echte Antworten der Bundesbank (10-jährige Bundeswertpapiere, 25.09. bis
  19.10.2026) und des US-Finanzministeriums (Treasury Par Yield Curve 2015, auf 5 Tage gekürzt),
  abgerufen am 19.10.2026 (Bauschritt 4).
- `damodaran/`: echte Seiten von Aswath Damodaran (NYU Stern), abgerufen am 19.10.2026.
  `Betas.html` und `wacc.html` auf wenige Branchen gekürzt, `ratings.html` und
  `ERPbymonth.xlsx` ungekürzt. Die Branchenliste `indname.xlsx` (8 MB) erzeugt
  `tests/test_kapitalmarkt.py` im Format der echten Datei mit wenigen Zeilen.
