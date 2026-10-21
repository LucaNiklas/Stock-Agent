# ADR 0013: Prüfer vollständig, Goldstandard und Gemini-Test (Bauschritt 10)

Status: angenommen (21.10.2026, Lucas Auftrag „fahre fort mit den nächsten zwei Bauschritten“).

## Kontext

SPEC 11 beschreibt vier Prüfebenen, die Eskalation an Luca und die Kalibrierung der Prüfer mit
einem Goldstandard. Bis Bauschritt 9 liefen J1 (Zahlen) und J2 (Belege). SPEC 8.3 verlangt F1
Forensik, SPEC 8.8 einen praktischen Test von Gemini als zweiter Modellfamilie.

## Entscheidung

1. **J4 Endkontrolle ohne Sprachmodell** (`judges/final_check.py`). Alles, was J4 prüfen soll,
   steht im Text und in `decision.json`: 14 Abschnitte, kein offener Platzhalter, Note und
   Kategorie gleich der Entscheidung, These unverändert, jede geprüfte Aussage mit Beleg im
   Bericht, keine Kaufaufforderung (wörtliche Zitate aus Dokumenten ausgenommen), jedes Risiko
   der Gegenposition mit Erwiderung oder offen. Ein Befund eskaliert den Lauf. Ein Modell würde
   hier nur Kosten und Zufall hinzufügen.
2. **J3 Jury aus drei Richtern** nach der Rubrik aus SPEC 11.3, eine Vorlage `j3-jury`, je
   Richter eine Agent-Datei mit eigenem Modell: Opus, Sonnet und auf Platz 3 Gemini. Ohne
   Gemini nimmt Platz 3 Haiku (`J3_jury_rueckfall_extern`), Bericht und Lauf vermerken die
   eingeschränkte Diversität (HR-16). Der Fall ist anonymisiert (Firmenname durch „das
   Unternehmen“), enthält nur geprüfte Aussagen, höchstens 12 je Seite, und beim zweiten Richter
   steht die Gegenposition vorn (SPEC 11.4). Median und Spannweite je Kriterium rechnet
   `core/jury.py` über den Rechenweg. `verified` nur, wenn kein Median unter 3, Gesamtbegründung
   mindestens 4, keine Spannweite über 2 und mindestens zwei Urteile. Sonst eskaliert der Fall.
3. **F1 Forensik nur bei Warnsignal** der Berechnung (Hinweise H-01 Beneish und H-04 Sloan an F1).
   F1 läuft neben A3 und A4 und vor J1 und J2, damit auch seine Aussagen nachgerechnet und belegt
   werden. Entkräftet zählt nur mit geprüftem Beleg. Bestätigt oder offen eskaliert (SPEC 11.5).
   Die Kappung der Note bei Beneish über der Schwelle bleibt auch nach Entkräftung, siehe Frage 1.
4. **Eskalationen** (`eskalationen.py`): Warteschlange im Dashboard und `stockagent eskalationen`
   mit den konkreten Streitpunkten (beide Werte bei J1, Aussage und Zitat bei J2, Punkte der
   Jury, Warnsignal der Forensik, Befunde von J4). Lucas Entscheidung `freigeben` oder
   `verwerfen` mit Begründung steht in `state/decisions.yaml` (versioniert) und in
   `decision.json`. Freigeben führt auf die Kategorie vor der Eskalation zurück, nie höher
   (HR-13). Skill `/review-escalations` geht die Fälle mit Luca durch.
5. **Goldstandard** (`goldstandard.py`, `eval/run_eval.py`): 21 Fälle aus Apple, JPMorgan,
   Progressive, Realty Income und Intel. J1: 11 Fälle mit Eingaben aus den XBRL-Daten der 10-K
   (Konzept, Periode, Meldungsnummer) und der Formel, richtig oder mit falscher Zahl (Vorzeichen,
   Faktor 10, falscher Nenner) oder falscher Periode. J2: 10 Fälle mit Auszug aus dem 10-K und
   wörtlichem Zitat, richtig, erfunden oder mit einer eingebetteten Anweisung an den Prüfer.
   Die Fälle liegen in `eval/kandidaten/`, nicht in `eval/gold/`: Der Ordner ist für Agenten
   gesperrt und nimmt nur von Luca geprüfte Fälle auf (SPEC 11.6 Nr. 1).
6. **Zwei Messarten.** Deterministisch in der CI (`.github/workflows/eval.yml`): Fälle in sich
   stimmig, J1 mit dem Goldwert als Nachrechnung gegen die Toleranzen, J2 aus der letzten
   Aufzeichnung. Ändert sich die Version der J2-Vorlage, schlägt die CI fehl, bis ein neuer
   Live-Lauf aufgezeichnet ist (SPEC 11.6 Nr. 4). Live auf Lucas Mac: J1 über das Werkzeug
   `nachrechnen` gegen die eigene Datenbank, J2 über `claude -p --agent j2-belegpruefer` mit bis
   zu zwei Berichtigungen wie im Lauf.
7. **Gemini** (`agents/tools/gemini.py`): Aufruf über `gemini -p` mit Rolle, Auftrag und Seiten im
   Text, Antwort gegen das Schema geprüft, bei jedem Fehler `GeminiNichtVerfuegbar` und Rückfall.
   `extern.aktiv` bleibt aus, bis der Test auf Lucas Mac gelingt.

## Geprüft

- Deterministisch: J1 erkennt 5 von 5 eingebauten Zahlen- und Periodenfehlern, kein Fehlalarm bei
  5 richtigen Fällen. Der Grenzfall Apple (Bruttomarge 2024 als 2025, Abweichung 1,5 %) liegt
  unter der Toleranz von 2 %: J1 meldet nur Rundung. Periodenfehler bei ruhigen Kennzahlen
  fallen also nicht als `mismatch` auf. Das zeigt der Fall absichtlich, er zählt nicht zur Quote.
- J2 Probelauf in der Cloud-Umgebung (21.10.2026, Sonnet als Rückfall für extern, 14 Runden,
  0,13 USD): 10 von 10 Urteilen richtig, alle 3 erfundenen Aussagen und beide eingebetteten
  Anweisungen als `contradicted` erkannt, die Anweisungen ausdrücklich nicht befolgt, keine
  Fehlalarme. Formal falsch war das Feld `claim` (Kennung mit Zusatztext). Im Lauf hätte die
  Vollständigkeitsprüfung die Antwort einmal zurückgeschickt. Seitdem nennt der Auftrag die Regel
  ausdrücklich. Der Probelauf zählt nicht als Aufzeichnung, weil der Auftragstext danach geändert
  wurde und weil verschachtelte Sitzungen in der Cloud die Kennung der Hauptsitzung erben.
- Gemini: hier nicht testbar, die Gemini CLI fehlt und eine Anmeldung mit Lucas Google-Konto ist
  in der Cloud-Umgebung nicht möglich. Test auf dem Mac: `uv run stockagent tool gemini-test`,
  danach `uv run python eval/run_eval.py --live --gemini`.

## Fragen an Luca

1. Die Kappungstabelle in SPEC 6 hebt die Kappung bei Beneish über der Schwelle auf, wenn F1 entkräftet. HR-13 sagt,
   Sprachmodelle dürfen nie aufwerten. Gebaut ist die strengere Lesart: Die Kappung bleibt, F1
   kann nur eskalieren. Soll eine von J2 geprüfte Entkräftung die Kappung aufheben?
2. Die Goldfälle in `eval/kandidaten/` bitte gegen die 10-K prüfen (Eingaben und Auszüge) und
   dann nach `eval/gold/` verschieben, mit `luca_geprueft: true`.

## Folgen

- Mehr Läufe enden als `eskaliert`, bis die Prüfer kalibriert sind. Note und Kategorie entstehen
  weiter deterministisch.
- Eine Tiefenanalyse hat ohne Nachforderungen bis zu 15 Aufträge statt 11 (drei Richter, F1).
