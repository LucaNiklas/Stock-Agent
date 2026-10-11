## 1. Was am Vorgängerdokument falsch, veraltet oder unvollständig war

Die folgende Tabelle ist das Ergebnis der Gegenprüfung. Die rechte Spalte sagt, was daraus für den Bau folgt.

| Nr. | Aussage in Version 1 | Befund (Stand Oktober 2026) | Konsequenz für das System |
|---|---|---|---|
| 1 | Meldepflicht für Directors' Dealings ab 5.000 EUR pro Jahr | Der EU Listing Act hat die Schwelle auf 20.000 EUR angehoben und nationalen Aufsichten erlaubt, sie auf bis zu 50.000 EUR zu erhöhen. Die BaFin hat per Allgemeinverfügung vom 4. Dezember 2025 die 50.000 EUR gewählt. | Deutsche Insider-Daten zeigen seitdem nur noch größere Geschäfte. Das Insider-Modul muss die Schwelle je Land und Datum als Konfigurationstabelle führen und darf Meldelücken nicht als "keine Käufe" deuten. |
| 2 | Rechtsgrundlage Paragraf 15a und 15b WpHG | Maßgeblich ist seit 2016 Art. 19 der Marktmissbrauchsverordnung (MAR), unmittelbar geltendes EU-Recht. | Quellenangaben und Doku auf Art. 19 MAR umstellen. |
| 3 | Meldepflicht auch für "Verwandte ersten Grades" | Erfasst sind eng verbundene Personen nach Art. 3 Abs. 1 Nr. 26 MAR. Das sind Ehe- und eingetragene Lebenspartner, unterhaltsberechtigte Kinder, Verwandte, die seit mindestens einem Jahr im selben Haushalt leben, sowie Gesellschaften, die von der Führungsperson geführt oder kontrolliert werden. | Das Feld `person_relation` im Datenmodell nutzt genau diese Kategorien. Käufe über eigene Holdings zählen als Insiderkauf. |
| 4 | Fehlte | Führungspersonen dürfen 30 Kalendertage vor Veröffentlichung eines Zwischen- oder Jahresberichts grundsätzlich nicht handeln (Art. 19 Abs. 11 MAR). | Das Insider-Modul kennt diese Sperrfenster. Ein Kauf direkt nach Ende des Sperrfensters ist normal und kein Sondersignal. |
| 5 | Ausführung über LS Exchange, Tradegate als Ausweichplatz, keine freie Börsenplatzwahl | Seit Juli 2026 ist Payment for Order Flow EU-weit verboten. Trade Republic hat die Exklusivität mit Lang & Schwarz beendet, routet nach eigenem Bestpreis-Algorithmus, betreibt ein eigenes multilaterales Handelssystem und bietet laut Vergleichsportalen über 20 Handelsplätze. | Spread- und Liquiditätsannahmen dürfen nicht mehr pauschal von LS Exchange ausgehen. Liquidität wird über das Handelsvolumen am Heimatmarkt gemessen. Die Liste der Handelsplätze ist ein veränderlicher Konfigurationswert. |
| 6 | Über 12.000 Aktien handelbar | Bestätigt, die Zahl ist durch die neuen Handelsplätze im Juli 2026 gestiegen. Trade Republic veröffentlicht weder eine offizielle API noch eine maschinenlesbare Instrumentenliste. Inoffizielle Bibliotheken wie `pytr` nutzen das private Websocket-Protokoll und können jederzeit brechen. | Das Universum entsteht aus den Listen handelbarer Aktien der deutschen Börsenplätze und breiten Indexbeständen (Abschnitt 7.1). Version 4 lädt die Liste aus der öffentlichen Produktübersicht von Trade Republic ohne Login (7.1). `pytr` wird nicht verwendet (HR-09). |
| 7 | PDF-Parsing (LlamaParse) als Hauptweg zur Kennzahlengewinnung | Das ist der fehleranfälligste Weg. In FinanceBench (Patronus AI, Contextual AI, Stanford) beantwortete GPT-4-Turbo mit gemeinsamem Vektorspeicher 81 Prozent der Fragen zu SEC-Berichten falsch oder gar nicht. Mit langem Kontext statt Retrieval lag die Trefferquote bei 79 Prozent. Für US-Werte liegen alle Abschlusszahlen strukturiert als XBRL bei der SEC vor, für EU-Emittenten an regulierten Märkten als ESEF-Inline-XBRL. | XBRL ist Primärquelle. PDF-Extraktion nur als Rückfall für Anhangangaben, Segmentdaten und Emittenten ohne XBRL. Arithmetik ausschließlich in Python. |
| 8 | Der Judge braucht dieselben Rohdaten wie der geprüfte Agent | Richtig, aber unvollständig. Das MARCH-Paper (Alibaba Qwen, ACL 2026) zeigt, dass ein Prüfer, der die Antwort des Erzeugers sieht, dessen Fehler übernimmt. Wirksam ist gezielte Informationsasymmetrie. | Der Zahlenprüfer rechnet blind nach und sieht das Ergebnis des Analyseagenten erst danach. |
| 9 | Judges weichen in Benchmarks um 15 bis 25 Prozent von Menschen ab | Für diese Spanne fand sich keine belastbare Quelle. Die Literatur zeigt Werte, die stark von Aufgabe und Prompt abhängen. Beim Agent-as-a-Judge-Paper (KAUST, Meta, Schmidhuber, ICML 2025) stimmte ein Judge mit Werkzeugzugriff in 90 Prozent der Fälle mit dem menschlichen Konsens überein, ein reiner LLM-Judge in 70 Prozent. | Keine fremde Fehlerquote übernehmen. Das System misst die Genauigkeit seiner eigenen Judges auf einem Goldstandard-Datensatz (Abschnitt 11.6). |
| 10 | Ein Distress-Modell erreichte in einer UK-Studie 83 Prozent Genauigkeit | Die Quelle ließ sich nicht verifizieren. | Nicht als Parameter verwenden. Distress-Risiko über Altman-Z und Zinsdeckung abbilden, beide mit dokumentierten Grenzen. |
| 11 | Debt-to-Equity unter 1 gilt als gut | Als Faustregel branchenabhängig und bei Banken, Versicherern und Immobiliengesellschaften sinnlos. Bei Firmen mit negativem Eigenkapital durch Aktienrückkäufe (häufig bei US-Großkonzernen) ist die Kennzahl nicht definiert. | Verschuldung über Nettoverschuldung zu EBITDA und Zinsdeckung messen. Banken, Versicherer und Immobilienwerte bekommen eigene Scorecards (Abschnitt 3.11). |
| 12 | Fehlte | Bessembinder (Journal of Financial Economics 2018) zeigt, dass die Mehrheit der US-Aktien seit 1926 über ihre Lebensdauer schlechter rentierte als einmonatige Staatsanleihen. Die besten rund 4 Prozent der Unternehmen erklären den gesamten Nettovermögenszuwachs des US-Marktes. | Einzeltitelauswahl ist eine Wette gegen eine stark schiefe Verteilung. Das System misst sich ab Tag 1 an einem Indexvergleich und hat vorab festgelegte Abbruchkriterien (Abschnitt 14). |
| 13 | Fehlte | McLean und Pontiff (Journal of Finance 2016) untersuchten 97 veröffentlichte Renditeprädiktoren. Deren Renditen lagen nach Veröffentlichung im Schnitt 58 Prozent niedriger als in der Originalstudie. | Faktor-Scores wie Piotroski oder Value dienen als Filter für Qualität und Risiko, nicht als Renditeversprechen. |
| 14 | Fehlte | Sprachmodelle kennen den Kursverlauf der Vergangenheit aus ihren Trainingsdaten. Backtests mit LLM-Urteilen für Zeiträume vor dem Trainingsstichtag sind dadurch verzerrt (Glasserman und Lin 2023, Sarkar und Vafa 2024). | LLM-gestützte Teile werden nur vorwärts bewertet (Notenkontrolle, 14.2). Rückwärts getestet werden nur die deterministischen Faktor-Teile (Abschnitt 14). |
| 15 | Fehlte | Das Baader-Depot (rund 55.000 EUR) bildet den MSCI World ab. Ein Kauf von zum Beispiel Microsoft erhöht ein bereits großes Gewicht. | In Version 4 zurückgestellt (Anhang A). |
| 16 | "Befreiungsbank" als Depotstelle | Gemeint ist sehr wahrscheinlich die Baader Bank, Depotbank mehrerer Broker und Robo-Advisor (unter anderem Scalable Capital). | Luca bestätigt den Anbieter. Für das System zählt nur, dass die Bestände als Eingabedatei vorliegen. |
| 17 | Lauf alle zwei Wochen, Neubewertung aller Kandidaten | Abschlussdaten ändern sich nur quartalsweise. Ein starres Zwei-Wochen-Raster ohne Haltelogik erzeugt Hin-und-Her-Empfehlungen. | Zweiwöchentlicher Lauf mit ereignisgesteuerter Neuanalyse (neuer Bericht, Insider-Cluster, Kursbewegung über Schwelle) und Hysterese bei Kauf und Verkauf (Abschnitt 9.5). |

Weiterhin korrekt und übernommen wurden die Kennzahlenkategorien, Nissim und Penman als methodischer Rahmen, die Meldefrist von drei Geschäftstagen für Directors' Dealings, die SEC-Insiderdaten über Form 4 und die Grundidee eines mehrstufigen Prüfsystems.

### 1.1 Änderungen in Version 3

| Thema | Version 2 | Version 3 |
|---|---|---|
| Abdeckung | harte Ausschlüsse nach Größe, Tagesumsatz und Branche | alle Unternehmen werden bewertet, Größe und Liquidität wirken auf Konfidenz, Risiko und Positionsgröße (3.1) |
| Finanzwerte | ausgeschlossen | eigene Scorecards für Banken, Versicherer, Immobilien, Holdings und Wachstumsfirmen ohne Gewinn (3.11) |
| Skala | ein Score 0 bis 100 | Note A bis E, Konfidenz K1 bis K4 und Risikoklasse R1 bis R5 als getrennte Achsen (6) |
| Rechnungslegung | nicht behandelt | 14 Normalisierungsregeln IFRS gegen US-GAAP inklusive IFRS 18 ab 2027 (4) |
| Währungen | nur Umrechnung in EUR | Regeln für Bestands- und Stromgrößen, DCF-Währung, Unterwährungen, ökonomisches Exposure (5) |
| Bestand | Halten oder Verkaufsprüfung nach Score | Thesenkarten, zehn Prüfregeln, Steuerrechnung, verhaltenswissenschaftlich begründete Verkaufsgründe (10) |
| Start | ein CLI-Befehl | sechs Startwege, Kategorie-Abfrage in zwei Runden, Laufplan mit Kosten (9.7 bis 9.9) |
| Format | Bericht mit fester Gliederung | Formelregister, 14 Pflichtabschnitte je Analyse, Ungereimtheiten-Katalog, Reproduzierbarkeit (12) |
| Regeln | sieben Grundregeln | 16 harte Regeln mit technischer Durchsetzung und Test (0.1) |
| GitHub und Prompts | nicht beschrieben | Repository, Workflows, Issues für Eskalationen (16.11 bis 16.14), Prompt-Bibliothek (17) |
| Modellnamen | im Dokument | nur Modellklassen, Zuordnung in `config/models.yaml` |

### 1.2 Änderungen in Version 4

| Thema | Version 3 | Version 4 |
|---|---|---|
| Umfang | Recherche plus Portfolio, Bestandsprüfung, Steuer, Gewichtungsvorschläge | nur Anzeigen und Bewerten, finanzieller Überblick je Unternehmen. Portfolio, Bestand und Steuer in Anhang A zurückgestellt |
| Universum | Börsenlisten plus Indexbestände, Handelbarkeit von Luca bestätigt | bei Trade Republic handelbare Aktien aus der öffentlichen Produktübersicht app.traderepublic.com/browse/stock (7.1) |
| Vorgehen | 14 Phasen | Bauschritte mit frühem nutzbarem Ergebnis (16.10) |
| HR-01 | Ziffern-Verbot für alle Agentenausgaben | nur für Freitextfelder, Zitate über Zitat-Gate, DCF-Annahmen als Stufen |
| HR-06 | Formeln nur in `registry.py` | Arithmetik nur in `core/`, Kennzahlen nur über die Registry |
| HR-13 | Sicherheitsmarge hing an LLM-Annahmen | Kategorie nur aus deterministischen Werten |
| Neue Regeln | | HR-17 Prompt-Injection, HR-18 Kostenlimit |
| Broker-Hook | Muster `order` | präzise Muster mit Test, `ORDER BY` erlaubt |
| Datenanbieter | Pflicht für Abgleich | optional, Default nur kostenlose Quellen |
| Branchencodes | Quelle offen | Reihenfolge in 7.8 |
| Fachlich | | negativer FCF im Reverse-DCF, Einordnung Mohanram, Teilfreistellung und Vorabpauschale in Anhang A |

### 1.3 Änderungen in Version 4.1

| Thema | Version 4.0 | Version 4.1 |
|---|---|---|
| Ausführung | Python-Orchestrator mit Agent SDK und API-Schlüssel | Subagents in Claude Code über Lucas Abo, Ablauf vom Python-Zustandsautomaten vorgegeben (15.1) |
| Modelle | Klassen ohne Zuordnung | Haiku für Suche und Sammeln, Sonnet für Texte und Prüfungen, Opus nur für Fundamentalanalyse, Bewertung, Gegenposition und Forensik (8.7) |
| Zweite Modellfamilie | API eines anderen Anbieters | Gemini optional über Lucas Google-Konto, Test in Schritt 10 (8.8) |
| HR-18 | Kostenlimit in EUR | Verbrauchsgrenzen je Lauf, Kosten in EUR nur im optionalen API-Betrieb |
