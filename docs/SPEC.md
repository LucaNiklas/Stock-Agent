# Stockpicking-Agent für Trade Republic
## Bauplan und Spezifikation für Claude Code (Stand 08.10.2026, Version 3.0)

Dieses Dokument ersetzt die Recherche-Grundlage vom 08.10.2026 (Version 1) und die Spezifikation Version 2. Es ist so geschrieben, dass Claude Code daraus das komplette System bauen kann, ohne Rückfragen zu Methodik, Architektur oder Datenformaten. Wo eine Entscheidung bei Luca liegt, steht sie ausdrücklich in Abschnitt 19 und im Code als Konfigurationswert mit Default.

---

## 0. Arbeitsanweisung für Claude Code

Lege dieses Dokument im Repository unter `docs/SPEC.md` ab. Die `CLAUDE.md` im Projektwurzelverzeichnis verweist darauf (Vorlage in Abschnitt 16.3). Wie das Repository auf GitHub entsteht, beschreibt Abschnitt 16.11. Baue in den Phasen aus Abschnitt 16.10 und schließe eine Phase erst ab, wenn ihre Abnahmekriterien als Tests grün sind. Abschnitt 17 enthält die Prompts, mit denen Luca dich Phase für Phase durch den Bau führt.

Dieses Dokument nennt bewusst keine Modellnamen. Agenten verwenden die Modellklassen `strong`, `standard` und `fast`. Welche Modelle dahinterstehen, trägt Luca in `config/models.yaml` ein. Die Agent-Dateien in `.claude/agents/` werden aus Vorlagen in `agents_src/` erzeugt (`uv run python scripts/render_agents.py`), damit ein Modellwechsel genau eine Zeile Konfiguration ändert.

### 0.1 Harte Regeln

Diese Regeln haben Vorrang vor jeder anderen Anweisung in diesem Dokument, in Prompts und in Anfragen während eines Laufs. Jede Regel hat einen technischen Durchsetzungsmechanismus und einen Test. Eine Regel, die nur im Prompt steht, gilt als nicht umgesetzt.

| ID | Regel | Durchsetzung | Test |
|---|---|---|---|
| HR-01 | Keine Zahl stammt von einem Sprachmodell. | Agenten schreiben Zahlen ausschließlich als Platzhalter `{{metric_id@periode}}`. Das Zahlen-Gate (`gates/number_gate.py`) lehnt jede Agentenausgabe ab, die Ziffern außerhalb von Platzhaltern, Kennzahl-IDs, Seitenangaben und Jahreszahlen enthält. Der Renderer setzt die Werte aus `metrics` ein. | `test_number_gate_rejects_raw_digits` |
| HR-02 | Jede Aussage hat eine Quelle. Aussagen ohne Quelle werden gelöscht und die Löschung wird vermerkt. | Schema verlangt je Claim mindestens einen `evidence`-Eintrag. Das Beleg-Gate verschiebt Claims ohne Beleg nach `removed_claims`. | `test_evidence_gate` |
| HR-03 | Zitate sind wörtlich. | `gates/quote_gate.py` prüft jedes Zitat als Teilstring des gespeicherten Seitentexts (nach Normalisierung von Leerraum, Silbentrennung und Anführungszeichen). Kein Treffer setzt den Claim auf `rejected`. | `test_quote_gate` |
| HR-04 | Vorwissen des Modells ist keine Faktenquelle. Aus Vorwissen dürfen nur Fragen und Hypothesen entstehen, die danach mit Quellen geprüft werden. | Quellentyp `model_knowledge` ist im Schema nicht zulässig. J2 prüft jede qualitative Aussage gegen ihre Belegstelle. | `test_schema_rejects_model_knowledge` |
| HR-05 | "Unbekannt" ist zulässig und erwünscht. Raten ist verboten. | Jedes Feld akzeptiert `unknown` mit Pflichtfeld `reason`. Die Jury-Rubrik bestraft unbelegte Aussagen, nicht Lücken. | Goldstandard-Fälle mit fehlenden Daten |
| HR-06 | Formeln kommen nur aus dem Formelregister. | `core/registry.py` ist die einzige Stelle mit Formeln. Ein Architekturtest verbietet arithmetische Ausdrücke auf Finanzgrößen in anderen Modulen. | `test_formulas_only_in_registry` |
| HR-07 | Point-in-Time. Keine Information nach dem Analysedatum. | Alle Datenzugriffe laufen über `store.pit_query(as_of=...)`. | `test_no_query_without_as_of` |
| HR-08 | Ungereimtheiten werden gemeldet, nie geglättet. | Katalog in Abschnitt 12.4. Der Berichtsabschnitt "Ungereimtheiten" ist Pflicht, auch wenn er leer ist, und listet die ausgeführten Prüfungen. | Snapshot-Test des Berichts |
| HR-09 | Keine Orders, kein Schreibzugriff auf Depots. | Hook `block_broker.sh`. Broker-Bibliotheken nur hinter einem Nur-Lese-Wrapper. | `test_hook_blocks_order` |
| HR-10 | Jede Analyse hat dasselbe Format. | Berichte entstehen nur aus Vorlage und Schema (Abschnitt 12). Freitext des Modells nur in definierten Feldern mit Längengrenze. | Snapshot-Tests |
| HR-11 | Agenten ändern zur Laufzeit weder Konfiguration noch Formeln noch Gewichte. | Konfiguration wird beim Start eingefroren und gehasht. Im Laufmodus fehlen Schreibrechte auf `config/`. | `test_config_frozen` |
| HR-12 | Jede Zahl trägt Währung, Einheit, Rechnungslegungsstandard und Periode. | Pydantic-Typen `Money` und `Fact` sind ohne diese Felder nicht konstruierbar. | Typprüfung mit mypy |
| HR-13 | Sprachmodelle können ein Unternehmen nur abwerten oder eskalieren, nie aufwerten. Note und Kategorie entstehen deterministisch. | Zustandsautomat in `core/decisions.py`. LLM-Ausgaben haben dort nur die Übergänge `escalate` und `downgrade`. | `test_llm_cannot_upgrade` |
| HR-14 | Prüfer arbeiten blind. | Der Orchestrator übergibt J1 die Claims ohne Werte. | `test_j1_input_has_no_values` |
| HR-15 | Keine punktgenauen Kursziele, keine Renditeversprechen, keine Kauf- oder Verkaufsbefehle. | Wortliste im Formulierungs-Gate und Prüfung durch J4. | `test_wording_gate` |
| HR-16 | Nichts wird verschwiegen. Fehlende Daten, übersprungene Titel, Kostenabbruch und eingeschränkte Jury-Diversität stehen im Bericht. | Pflichtabschnitt "Grenzen dieses Laufs". | Snapshot-Test |

Null Halluzination kann kein Sprachmodell garantieren. Anthropics eigene Dokumentation beschreibt wörtliche Zitate, Belegpflicht, die ausdrückliche Erlaubnis zu "Ich weiß es nicht" und den Ausschluss von Vorwissen als Techniken, die Halluzinationen verringern, aber nicht beseitigen. Das System garantiert deshalb etwas Prüfbares. Keine ungeprüfte Zahl und keine unbelegte Aussage erreicht den Bericht. Halluziniert ein Agent, fängt es eine der Schranken ab, der Vorfall wird gezählt und fließt in die Prüferkalibrierung (Abschnitt 11.6).

---

## 1. Was am Vorgängerdokument falsch, veraltet oder unvollständig war

Die folgende Tabelle ist das Ergebnis der Gegenprüfung. Die rechte Spalte sagt, was daraus für den Bau folgt.

| Nr. | Aussage in Version 1 | Befund (Stand Oktober 2026) | Konsequenz für das System |
|---|---|---|---|
| 1 | Meldepflicht für Directors' Dealings ab 5.000 EUR pro Jahr | Der EU Listing Act hat die Schwelle auf 20.000 EUR angehoben und nationalen Aufsichten erlaubt, sie auf bis zu 50.000 EUR zu erhöhen. Die BaFin hat per Allgemeinverfügung vom 4. Dezember 2025 die 50.000 EUR gewählt. | Deutsche Insider-Daten zeigen seitdem nur noch größere Geschäfte. Das Insider-Modul muss die Schwelle je Land und Datum als Konfigurationstabelle führen und darf Meldelücken nicht als "keine Käufe" deuten. |
| 2 | Rechtsgrundlage Paragraf 15a und 15b WpHG | Maßgeblich ist seit 2016 Art. 19 der Marktmissbrauchsverordnung (MAR), unmittelbar geltendes EU-Recht. | Quellenangaben und Doku auf Art. 19 MAR umstellen. |
| 3 | Meldepflicht auch für "Verwandte ersten Grades" | Erfasst sind eng verbundene Personen nach Art. 3 Abs. 1 Nr. 26 MAR. Das sind Ehe- und eingetragene Lebenspartner, unterhaltsberechtigte Kinder, Verwandte, die seit mindestens einem Jahr im selben Haushalt leben, sowie Gesellschaften, die von der Führungsperson geführt oder kontrolliert werden. | Das Feld `person_relation` im Datenmodell nutzt genau diese Kategorien. Käufe über eigene Holdings zählen als Insiderkauf. |
| 4 | Fehlte | Führungspersonen dürfen 30 Kalendertage vor Veröffentlichung eines Zwischen- oder Jahresberichts grundsätzlich nicht handeln (Art. 19 Abs. 11 MAR). | Das Insider-Modul kennt diese Sperrfenster. Ein Kauf direkt nach Ende des Sperrfensters ist normal und kein Sondersignal. |
| 5 | Ausführung über LS Exchange, Tradegate als Ausweichplatz, keine freie Börsenplatzwahl | Seit Juli 2026 ist Payment for Order Flow EU-weit verboten. Trade Republic hat die Exklusivität mit Lang & Schwarz beendet, routet nach eigenem Bestpreis-Algorithmus, betreibt ein eigenes multilaterales Handelssystem und bietet laut Vergleichsportalen über 20 Handelsplätze. | Spread- und Liquiditätsannahmen dürfen nicht mehr pauschal von LS Exchange ausgehen. Liquidität wird über das Handelsvolumen am Heimatmarkt gemessen. Die Liste der Handelsplätze ist ein veränderlicher Konfigurationswert. |
| 6 | Über 12.000 Aktien handelbar | Bestätigt, die Zahl ist durch die neuen Handelsplätze im Juli 2026 gestiegen. Trade Republic veröffentlicht weder eine offizielle API noch eine maschinenlesbare Instrumentenliste. Inoffizielle Bibliotheken wie `pytr` nutzen das private Websocket-Protokoll und können jederzeit brechen. | Das Universum entsteht aus den Listen handelbarer Aktien der deutschen Börsenplätze und breiten Indexbeständen (Abschnitt 7.1). Die Handelbarkeit bei Trade Republic bestätigt Luca für Kaufkandidaten. `pytr` bleibt optional und standardmäßig deaktiviert. |
| 7 | PDF-Parsing (LlamaParse) als Hauptweg zur Kennzahlengewinnung | Das ist der fehleranfälligste Weg. In FinanceBench (Patronus AI, Contextual AI, Stanford) beantwortete GPT-4-Turbo mit gemeinsamem Vektorspeicher 81 Prozent der Fragen zu SEC-Berichten falsch oder gar nicht. Mit langem Kontext statt Retrieval lag die Trefferquote bei 79 Prozent. Für US-Werte liegen alle Abschlusszahlen strukturiert als XBRL bei der SEC vor, für EU-Emittenten an regulierten Märkten als ESEF-Inline-XBRL. | XBRL ist Primärquelle. PDF-Extraktion nur als Rückfall für Anhangangaben, Segmentdaten und Emittenten ohne XBRL. Arithmetik ausschließlich in Python. |
| 8 | Der Judge braucht dieselben Rohdaten wie der geprüfte Agent | Richtig, aber unvollständig. Das MARCH-Paper (Alibaba Qwen, ACL 2026) zeigt, dass ein Prüfer, der die Antwort des Erzeugers sieht, dessen Fehler übernimmt. Wirksam ist gezielte Informationsasymmetrie. | Der Zahlenprüfer rechnet blind nach und sieht das Ergebnis des Analyseagenten erst danach. |
| 9 | Judges weichen in Benchmarks um 15 bis 25 Prozent von Menschen ab | Für diese Spanne fand sich keine belastbare Quelle. Die Literatur zeigt Werte, die stark von Aufgabe und Prompt abhängen. Beim Agent-as-a-Judge-Paper (KAUST, Meta, Schmidhuber, ICML 2025) stimmte ein Judge mit Werkzeugzugriff in 90 Prozent der Fälle mit dem menschlichen Konsens überein, ein reiner LLM-Judge in 70 Prozent. | Keine fremde Fehlerquote übernehmen. Das System misst die Genauigkeit seiner eigenen Judges auf einem Goldstandard-Datensatz (Abschnitt 11.6). |
| 10 | Ein Distress-Modell erreichte in einer UK-Studie 83 Prozent Genauigkeit | Die Quelle ließ sich nicht verifizieren. | Nicht als Parameter verwenden. Distress-Risiko über Altman-Z und Zinsdeckung abbilden, beide mit dokumentierten Grenzen. |
| 11 | Debt-to-Equity unter 1 gilt als gut | Als Faustregel branchenabhängig und bei Banken, Versicherern und Immobiliengesellschaften sinnlos. Bei Firmen mit negativem Eigenkapital durch Aktienrückkäufe (häufig bei US-Großkonzernen) ist die Kennzahl nicht definiert. | Verschuldung über Nettoverschuldung zu EBITDA und Zinsdeckung messen. Banken, Versicherer und Immobilienwerte bekommen eigene Scorecards (Abschnitt 3.11). |
| 12 | Fehlte | Bessembinder (Journal of Financial Economics 2018) zeigt, dass die Mehrheit der US-Aktien seit 1926 über ihre Lebensdauer schlechter rentierte als einmonatige Staatsanleihen. Die besten rund 4 Prozent der Unternehmen erklären den gesamten Nettovermögenszuwachs des US-Marktes. | Einzeltitelauswahl ist eine Wette gegen eine stark schiefe Verteilung. Das System misst sich ab Tag 1 an einem Indexvergleich und hat vorab festgelegte Abbruchkriterien (Abschnitt 14). |
| 13 | Fehlte | McLean und Pontiff (Journal of Finance 2016) untersuchten 97 veröffentlichte Renditeprädiktoren. Deren Renditen lagen nach Veröffentlichung im Schnitt 58 Prozent niedriger als in der Originalstudie. | Faktor-Scores wie Piotroski oder Value dienen als Filter für Qualität und Risiko, nicht als Renditeversprechen. |
| 14 | Fehlte | Sprachmodelle kennen den Kursverlauf der Vergangenheit aus ihren Trainingsdaten. Backtests mit LLM-Urteilen für Zeiträume vor dem Trainingsstichtag sind dadurch verzerrt (Glasserman und Lin 2023, Sarkar und Vafa 2024). | LLM-gestützte Teile werden nur vorwärts im Papierdepot bewertet. Rückwärts getestet werden nur die deterministischen Faktor-Teile (Abschnitt 14). |
| 15 | Fehlte | Das Baader-Depot (rund 55.000 EUR) bildet den MSCI World ab. Ein Kauf von zum Beispiel Microsoft erhöht ein bereits großes Gewicht. | Das Portfoliomodul rechnet die Durchschau-Gewichte aller ETFs und Fonds und bewertet Kandidaten nach ihrem Beitrag zur Diversifikation. |
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

---

## 2. Ausgangslage und was das Portfolio wirklich bedeutet

### 2.1 Bestände (Stand 08.10.2026, von Luca angegeben)

| Position | Betrag in EUR | Anteil am Gesamtvermögen |
|---|---|---|
| ETFs bei Trade Republic | 7.900 | 11,7 % |
| ETFs und Fonds bei Baader (MSCI-World-nah) | 55.000 | 81,2 % |
| Einzelaktien bei Trade Republic | 2.400 | 3,5 % |
| Anleihen | 400 | 0,6 % |
| Krypto | 470 | 0,7 % |
| Summe | 67.770 | 100 % |

ETFs und Fonds machen zusammen 62.900 EUR aus, also 92,8 Prozent.

### 2.2 Die Zielallokation ist eine große Entscheidung

Bezieht sich das Ziel "60 bis 70 Prozent ETFs, Rest Einzelaktien" auf das Gesamtvermögen, müssten Einzelaktien 30 bis 40 Prozent ausmachen. Das wären heute 20.300 bis 27.100 EUR statt 2.400 EUR, also das Acht- bis Elffache. Wer dafür ETF-Anteile verkauft, realisiert Kursgewinne und zahlt Abgeltungsteuer. Der naheliegende Weg ist, den Einzelaktienanteil über neue Sparraten aufzubauen.

Bezieht sich das Ziel nur auf das Trade-Republic-Depot (12.770 EUR), ist der Einzelaktienanteil mit 19 Prozent schon nahe am Ziel.

Das System behandelt beides als Konfiguration. In `config/portfolio.yaml` stehen `allocation_scope` (`total` oder `trade_republic`), `target_etf_share_min` und `target_etf_share_max`. Der Default ist `total` mit 0,60 und 0,70, damit die Rechnung sichtbar wird. Luca entscheidet (Abschnitt 19).

### 2.3 Was das System leisten soll und was nicht

Das System ist ein Recherche-Assistent. Es liefert alle zwei Wochen eine geprüfte, belegte Shortlist mit Bewertung, Gegenargumenten, Gewichtungsvorschlag und vollständiger Herleitung. Es trifft keine Anlageentscheidung und gibt keine Anlageberatung im rechtlichen Sinn. Kauf und Verkauf bleiben manuelle Schritte in der Trade-Republic-App.

Kosten bei Trade Republic sind 1 EUR Fremdkostenpauschale je Order, Sparpläne sind kostenlos und Bruchstücke ab 1 EUR möglich. Damit die Fixkosten unter 0,5 Prozent bleiben, setzt das System eine Mindestordergröße von 200 EUR (`min_order_eur`), außer bei Sparplänen.

---

## 3. Bewertungsmethodik

Die Methodik folgt einer festen Reihenfolge. Jede Stufe ist ein eigenes Modul mit eigener Versionsnummer (`methodology_version`).

```
Universum (alle Unternehmen) -> Klassifikation (Scorecard, Größe, Liquidität)
-> Datenqualität und Konfidenz -> Normalisierung Rechnungslegung und Währung
-> Kennzahlen und Trends -> Qualitäts- und Risiko-Scores -> Bewertung
-> Note, Konfidenz, Risikoklasse für alle Unternehmen
-> Tiefenanalyse für gewählte Kategorie und Bestand mit qualitativer Analyse,
   Insider-Signal, Gegenposition, Verifikation
-> Portfolio-Passung und Bestandsprüfung -> Entscheidungsvorlage
```

### 3.1 Vollabdeckung statt Ausschluss (Stufe 1)

Jedes Unternehmen im Universum wird bewertet. Es gibt keine Mindestgröße, keinen Mindestumsatz an der Börse und keinen Branchenausschluss. Merkmale, die in Version 2 zum Ausschluss führten, wirken jetzt auf drei andere Arten. Sie senken den Konfidenzgrad (wie belastbar ist die Note), sie erhöhen die Risikoklasse und sie begrenzen die vorgeschlagene Positionsgröße. Die Skala dazu steht in Abschnitt 6.

Die Forschung stützt diese Trennung. Fama und French (2008, "Dissecting Anomalies", Journal of Finance) zeigen, dass Mikrowerte zwar nur rund 3 Prozent des Börsenwerts, aber rund 60 Prozent aller Titel ausmachen und gleichgewichtete Ergebnisse dominieren. Hou, Xue und Zhang (2020, "Replicating Anomalies", Review of Financial Studies) finden, dass ein Großteil veröffentlichter Anomalien verschwindet, wenn man Mikrowerte richtig behandelt. Kennzahlen kleiner Firmen sind also statistisch weniger verlässlich, aber nicht wertlos. Amihud und Mendelson (1986, Journal of Financial Economics) und Amihud (2002, Journal of Financial Markets) zeigen, dass illiquide Aktien im Mittel höhere erwartete Renditen als Ausgleich für höhere Handelskosten haben. Für einen Anleger mit 15 bis 20 Jahren Horizont ist geringe Liquidität deshalb ein Kosten- und Risikomerkmal und kein Ausschlussgrund.

| Merkmal | Wirkung |
|---|---|
| Größenklasse nach Marktkapitalisierung (Nano unter 50 Mio. EUR, Micro 50 bis 300 Mio., Small 300 Mio. bis 2 Mrd., Mid 2 bis 10 Mrd., Large 10 bis 200 Mrd., Mega über 200 Mrd.) | Konfidenz (Micro und Nano höchstens K3), Risikoklasse, Vergleichsgruppe zusätzlich nach Größe |
| Illiquidität nach Amihud, ILLIQ = Mittelwert über 250 Handelstage von abs(Tagesrendite) / Tagesumsatz in EUR | Risikoklasse. Positionsgrenze je Order höchstens 1 Prozent des durchschnittlichen Tagesumsatzes (`max_order_pct_adv`). Hinweis auf Limit-Order im Bericht |
| Datenhistorie unter 5 Jahren | Konfidenz sinkt. Trendsäule mit verfügbarer Historie. Unter 2 Jahren Status "nicht bewertbar (Historie)" mit Anzeige der vorhandenen Werte |
| Going-Concern-Hinweis, versagter oder eingeschränkter Bestätigungsvermerk | Stopp-Flag, Note höchstens D (Abschnitt 6.2) |
| Lokale Rechnungslegung (HGB-Konzern ohne IFRS, J-GAAP, Ind AS, chinesische ASBE und andere) | Bewertung mit Konfidenz höchstens K3 (Abschnitt 4) |
| Banken, Versicherer, Immobilien, Holdings | eigene Scorecard (Abschnitt 3.11) |
| SPAC, Mantelgesellschaft, Fonds, ETF, Zertifikat | Status "kein operatives Unternehmen". Wird gelistet, bekommt aber keine Fundamentalnote |
| Laufendes Übernahmeangebot | Note wird berechnet, Hinweis "Kurs wird vom Angebot bestimmt" |
| Mehrfachlistings (ADR, Zweitnotiz) | technisch auf den Emittenten (LEI) zusammengeführt, alle Handelsplätze bleiben sichtbar |

"Nicht bewertbar" ist ein sichtbarer Status mit Grund. Kein Unternehmen verschwindet stillschweigend aus dem Universum.

### 3.2 Datenqualitätsprüfung (Stufe 2)

Die Ergebnisse landen als `dq_flags` am Unternehmen und bestimmen den Konfidenzgrad (6.3). Ein Stopp setzt die betroffenen Werte auf `unknown`, das Unternehmen bleibt im Universum.

1. Bilanzgleichung je Periode (Aktiva gleich Passiva, Toleranz 0,5 Prozent).
2. Konsistenz mit der XBRL-Berechnungsstruktur (Summen der Unterpositionen gleich Summenposition).
3. Einheiten und Skalierung (Tausend, Millionen) eindeutig, Währung je Wert gesetzt.
4. Periodenlogik stimmt (Geschäftsjahr mit abweichendem Stichtag korrekt zugeordnet, Quartale ergeben TTM ohne Doppelzählung).
5. Abgleich zweier unabhängiger Quellen für die Kernwerte Umsatz, operatives Ergebnis, Jahresüberschuss, operativer Cashflow, Investitionen, Bilanzsumme, Eigenkapital, Finanzschulden, Aktienanzahl. Abweichung über 1 Prozent erzeugt eine Warnung, über 5 Prozent einen Stopp.
6. Ausreißerprüfung gegen die eigene Historie (robuste z-Werte über Median und MAD, Schwelle 4). Ein Ausreißer ist kein Fehler, braucht aber eine Begründung aus dem Bericht, etwa eine Übernahme.
7. Restatements erkennen. Wenn ein späterer Bericht Vorjahreswerte ändert, werden beide Fassungen gespeichert und die Änderung markiert.
8. Aktienanzahl um Splits und Aktiendividenden bereinigt.

### 3.3 Kennzahlenkatalog

Jede Kennzahl ist in `config/metrics.yaml` als Formel mit ID, Version, Eingabekonzepten und Sektorhinweisen hinterlegt. Die Berechnung liest nur diese Definitionen. So kommt eine neue Kennzahl ohne Codeänderung dazu.

Durchschnittswerte für Bestandsgrößen sind (Anfang plus Ende) durch 2. TTM bedeutet Summe der letzten vier Quartale.

**Profitabilität**

| ID | Formel | Hinweis |
|---|---|---|
| gross_margin | Bruttoergebnis / Umsatz | Nicht bei Umsatzkostenverfahren ohne Bruttoergebnis berechenbar, dann leer lassen |
| ebit_margin | EBIT / Umsatz | |
| fcf_margin | Free Cashflow / Umsatz | |
| gp_to_assets | Bruttoergebnis / Bilanzsumme | Novy-Marx (2013), gilt als starkes Qualitätsmaß |
| roe | Jahresüberschuss / durchschnittliches Eigenkapital | Bei negativem Eigenkapital nicht definiert |
| roa | Jahresüberschuss / durchschnittliche Bilanzsumme | |
| roic | NOPAT / durchschnittliches investiertes Kapital | NOPAT = EBIT mal (1 minus Steuersatz). Investiertes Kapital = Eigenkapital plus Finanzschulden plus Leasingverbindlichkeiten minus liquide Mittel |
| dupont | ROE = Nettomarge mal Kapitalumschlag mal Hebel | Zerlegung zeigt, ob Rendite aus Marge oder Verschuldung kommt |

**Wachstum**

| ID | Formel | Hinweis |
|---|---|---|
| revenue_cagr_3y, revenue_cagr_5y | (Wert t / Wert t-n) hoch (1/n) minus 1 | Organisches Wachstum aus Bericht übernehmen, wenn verfügbar |
| eps_cagr_5y | analog auf verwässertem Ergebnis je Aktie | Durch Rückkäufe getriebenes Wachstum separat ausweisen |
| fcf_per_share_cagr_5y | analog | |
| share_count_change_3y | Aktienanzahl t / t-3 minus 1 | Verwässerung ist negativer Faktor |

**Cashflow und Ertragsqualität**

| ID | Formel | Hinweis |
|---|---|---|
| fcf | Operativer Cashflow minus Investitionen in Sachanlagen und immaterielle Werte | Unter IFRS 16 zusätzlich Tilgung von Leasingverbindlichkeiten abziehen, um mit US-GAAP vergleichbar zu sein. Beide Varianten speichern |
| fcf_conversion | FCF / Jahresüberschuss | Dauerhaft unter 0,8 ist ein Warnsignal |
| ocf_to_net_income | Operativer Cashflow / Jahresüberschuss | |
| sloan_accruals | (Jahresüberschuss minus operativer Cashflow) / durchschnittliche Bilanzsumme | Sloan (1996). Hohe Accruals gehen historisch mit schwächeren Folgerenditen einher |
| sbc_to_revenue | Aktienbasierte Vergütung / Umsatz | Bei Tech-Firmen oft wesentlicher Kostenblock, der im FCF fehlt |
| fcf_after_sbc | FCF minus aktienbasierte Vergütung | Konservative Variante |

**Bilanz und Finanzierung**

| ID | Formel | Hinweis |
|---|---|---|
| net_debt | Finanzschulden plus Leasingverbindlichkeiten minus liquide Mittel und kurzfristige Wertpapiere | Pensionsrückstellungen getrennt ausweisen (`net_debt_incl_pensions`), wichtig bei deutschen Industriewerten |
| net_debt_to_ebitda | Nettoverschuldung / EBITDA | Unter 2 komfortabel, über 3,5 erhöhtes Risiko, branchenabhängig |
| interest_coverage | EBIT / Zinsaufwand | Unter 3 ist kritisch |
| current_ratio | Umlaufvermögen / kurzfristige Verbindlichkeiten | Trend wichtiger als Niveau |
| quick_ratio | (Umlaufvermögen minus Vorräte) / kurzfristige Verbindlichkeiten | |
| equity_ratio | Eigenkapital / Bilanzsumme | |
| debt_maturity_12m | Finanzschulden fällig in 12 Monaten / liquide Mittel plus ungenutzte Kreditlinien | Refinanzierungsrisiko |

**Kapitalallokation**

| ID | Formel | Hinweis |
|---|---|---|
| payout_fcf | (Dividenden plus Rückkäufe) / FCF | Über 1 dauerhaft nur über Schulden finanzierbar |
| buyback_yield | Netto-Rückkäufe / Marktkapitalisierung | |
| shareholder_yield | Dividendenrendite plus Netto-Rückkaufrendite plus Nettoschuldenabbau / Marktkapitalisierung | |
| capex_to_depreciation | Investitionen / Abschreibungen | Dauerhaft unter 1 kann auf Substanzverzehr deuten |
| acquisition_intensity | Ausgaben für Übernahmen / operativer Cashflow (5 Jahre) | Hohe Werte machen organisches Wachstum schwer erkennbar |

**Bewertung**

| ID | Formel | Hinweis |
|---|---|---|
| enterprise_value | Marktkapitalisierung plus Nettoverschuldung plus Minderheitsanteile plus Pensionsdefizit minus nicht betriebsnotwendige Beteiligungen | Brücke einzeln speichern |
| ev_ebit | EV / EBIT (TTM und nächstes Jahr, falls Konsens verfügbar) | Vorzugskennzahl für Vergleiche über Kapitalstrukturen hinweg |
| ev_sales | EV / Umsatz | Für Firmen mit negativem EBIT |
| pe | Kurs / verwässertes EPS | Nur bei positivem Ergebnis |
| fcf_yield | FCF / Marktkapitalisierung | |
| pb | Kurs / Buchwert je Aktie | |
| dividend_yield | Dividende je Aktie / Kurs | |

Jede Bewertungskennzahl wird dreifach eingeordnet. Gegen die eigene Historie (Perzentil der letzten 10 Jahre), gegen die Vergleichsgruppe (Perzentil innerhalb der Branche, Branchenschlüssel aus SIC bei US-Werten und NACE bei EU-Werten, weil GICS lizenzpflichtig ist) und gegen den Gesamtmarkt.

### 3.4 Trend- und Zeitreihenanalyse

1. Mindestens 5, wenn verfügbar 10 Geschäftsjahre. Dazu die letzten 8 Quartale für TTM-Werte.
2. Für jede Kennzahl werden Niveau, Veränderung zum Vorjahr, 3- und 5-Jahres-CAGR, Standardabweichung und Trendsteigung (Theil-Sen-Schätzer, unempfindlich gegen Ausreißer) gespeichert.
3. Margenstabilität zählt so viel wie Margenniveau. Die Schwankungsbreite der EBIT-Marge über 10 Jahre geht in den Qualitätsscore ein.
4. Zyklische Branchen (Rohstoffe, Chemie, Halbleiter, Auto) werden über den gesamten Zyklus bewertet. Bewertungskennzahlen nutzen dort zusätzlich das durchschnittliche EBIT der letzten 7 bis 10 Jahre (`ev_ebit_normalized`).
5. Sondereffekte (Wertminderungen, Veräußerungsgewinne, Restrukturierung) werden aus dem Bericht übernommen und als bereinigte Zweitreihe gespeichert. Die unbereinigte Reihe bleibt maßgeblich, die bereinigte dient der Erklärung.
6. Vertikale Analyse je Jahr (alle Posten in Prozent vom Umsatz beziehungsweise von der Bilanzsumme) für die Detailansicht.

### 3.5 Qualitäts- und Risiko-Scores

Diese Scores sind etablierte Screening-Werkzeuge mit bekannten Grenzen. Sie gehen als Filter und Teilwerte ein, nie als alleinige Kaufbegründung.

**Piotroski F-Score (0 bis 9 Punkte, Piotroski 2000).** Je ein Punkt für ROA größer null, operativer Cashflow größer null, ROA gestiegen, operativer Cashflow größer Jahresüberschuss (bezogen auf die Bilanzsumme), langfristige Verschuldungsquote gesunken, Current Ratio gestiegen, keine neuen Aktien ausgegeben, Bruttomarge gestiegen, Kapitalumschlag gestiegen. Default-Schwelle für "solide" ist 6 oder mehr.

**Altman Z-Score.** Für produzierende Unternehmen gilt Z = 1,2 X1 + 1,4 X2 + 3,3 X3 + 0,6 X4 + 1,0 X5 mit X1 = Working Capital / Bilanzsumme, X2 = Gewinnrücklagen / Bilanzsumme, X3 = EBIT / Bilanzsumme, X4 = Marktkapitalisierung / Gesamtverbindlichkeiten, X5 = Umsatz / Bilanzsumme. Unter 1,81 liegt die Gefahrenzone, über 2,99 die sichere Zone. Für Nicht-Produzenten gilt Z'' = 6,56 X1 + 3,26 X2 + 6,72 X3 + 1,05 X4 mit X4 = Buchwert Eigenkapital / Gesamtverbindlichkeiten, Gefahrenzone unter 1,1, sichere Zone über 2,6. Das Modell stammt aus US-Daten der 1960er Jahre. Es dient als Warnlampe, nicht als Wahrscheinlichkeit.

**Beneish M-Score (8 Variablen).** M = minus 4,84 + 0,920 DSRI + 0,528 GMI + 0,404 AQI + 0,892 SGI + 0,115 DEPI minus 0,172 SGAI + 4,679 TATA minus 0,327 LVGI. Werte über minus 1,78 gelten als Hinweis auf mögliche Ergebnismanipulation und führen zur Eskalation an den Forensik-Agenten, nicht zum automatischen Ausschluss.

**Accruals (Sloan).** Höchstes Dezil innerhalb der Branche erzeugt ein Warnflag.

**Qualitätskomposit (angelehnt an Asness, Frazzini und Pedersen, "Quality minus Junk", 2019).** Vier Säulen mit Branchenperzentilen. Profitabilität (gp_to_assets, roic, fcf_margin), Wachstum (5-Jahres-Veränderung derselben Größen), Sicherheit (niedrige Verschuldung, niedrige Ergebnisvolatilität, Altman-Zone) und Ausschüttung (shareholder_yield, geringe Verwässerung). Gleich gewichtet, Ergebnis 0 bis 100.

### 3.6 Bewertung

Das System nennt nie einen einzelnen Kursziel-Wert. Es zeigt Spannen und macht sichtbar, welche Annahmen der aktuelle Kurs bereits enthält.

**Reverse-DCF (Hauptverfahren).** Gegeben sind aktueller Unternehmenswert, Kapitalkosten und Endwachstum. Gesucht ist das FCF-Wachstum der nächsten 10 Jahre, das den Kurs rechtfertigt. Diese implizite Wachstumsrate wird mit der eigenen Historie (5- und 10-Jahres-CAGR) und mit der Branche verglichen. Liegt sie weit über allem, was das Unternehmen je erreicht hat, ist die Aktie teuer, egal wie gut das Geschäft ist.

**DCF in drei Szenarien.** Bear, Base und Bull mit expliziten Annahmen zu Umsatzwachstum, Marge, Investitionsquote und Working Capital. Die Annahmen schlägt der Bewertungsagent vor und begründet jede mit Quellen. Python rechnet. Regeln für die Rechnung:

1. FCFF-Ansatz über 10 Jahre, danach Endwert nach Gordon-Wachstumsmodell.
2. Endwachstum höchstens der langfristige risikofreie Zins der Berichtswährung, Default höchstens 2,5 Prozent.
3. Kapitalkosten (WACC) aus risikofreiem Zins (10-jährige Bundesanleihe für EUR, 10-jährige Treasury für USD, aus offiziellen Quellen geladen), Aktienrisikoprämie (Default ist die implizite Prämie nach Damodaran, monatlich aktualisiert und als Wert mit Datum gespeichert), Beta (Branchenbeta nach Damodaran bereinigt um die eigene Verschuldung, weil Einzelbetas stark schwanken) und Fremdkapitalkosten nach Steuern.
4. Sensitivitätsmatrix über WACC (plus/minus 1 Prozentpunkt) und Endwachstum (plus/minus 0,5 Prozentpunkte).
5. Anteil des Endwerts am Gesamtwert wird ausgewiesen. Über 75 Prozent erzeugt einen Hinweis, dass der Wert fast nur von Annahmen über die ferne Zukunft abhängt.
6. Brücke von Unternehmenswert zu Eigenkapitalwert mit allen Posten aus `enterprise_value`.

**Multiples.** EV/EBIT, FCF-Rendite und KGV gegen Historie und Vergleichsgruppe. Daraus eine Spanne über das 25. bis 75. Perzentil der Vergleichsgruppe.

**Zusammenführung als "Football Field".** Alle Spannen in einem Diagramm, dazu der aktuelle Kurs. Die Sicherheitsmarge ist der Abstand zwischen Kurs und Base-Szenario. Default-Anforderung für einen Kaufkandidaten ist eine Sicherheitsmarge von mindestens 15 Prozent (`min_margin_of_safety`) oder eine implizite Wachstumsrate im Reverse-DCF unter der 5-Jahres-Historie.

### 3.7 Qualitative Analyse

Die qualitative Analyse liest Textteile der Berichte. Jede Aussage braucht eine Belegstelle.

| Thema | Leitfrage | Typische Quelle |
|---|---|---|
| Geschäftsmodell | Womit verdient das Unternehmen Geld, wie wiederkehrend sind die Umsätze? | Lagebericht, Item 1 im 10-K |
| Wettbewerbsvorteil | Woran zeigt sich ein Vorteil in den Zahlen (stabile Bruttomarge, hoher ROIC über Zyklen)? | Kennzahlen plus Lagebericht |
| Segmente | Welche Segmente wachsen und tragen den Gewinn? | Segmentberichterstattung |
| Kundenkonzentration | Gibt es Kunden über 10 Prozent des Umsatzes? | Anhang |
| Risikofaktoren | Was ist neu im Vergleich zum Vorjahr? | Risikobericht, Item 1A. Der Agent vergleicht beide Jahre Absatz für Absatz |
| Management und Anreize | Woran ist die Vergütung gekoppelt, wie viel Eigenbesitz besteht? | Vergütungsbericht, Proxy Statement (DEF 14A) |
| Kapitalallokation | Wie wurden Übernahmen der letzten 5 Jahre bewertet, gab es Wertminderungen darauf? | Anhang Goodwill |
| Bilanzpolitik | Wechsel des Abschlussprüfers, geänderte Bilanzierungsmethoden, Geschäfte mit nahestehenden Personen | Anhang, Bestätigungsvermerk |
| Prüfungsschwerpunkte | Was hat der Abschlussprüfer als besonders wichtig hervorgehoben (Key Audit Matters, Critical Audit Matters)? | Bestätigungsvermerk |

### 3.8 Insider-Signal

Die Forschung ist eindeutig in einem Punkt. Nicht jeder Insiderkauf trägt Information. Cohen, Malloy und Pomorski (Journal of Finance 2012) trennen routinemäßige von opportunistischen Insidern. Als routinemäßig gilt, wer in den drei Vorjahren jeweils im selben Kalendermonat gehandelt hat. Mehr als die Hälfte aller Insidergeschäfte war routinemäßig und ohne Vorhersagekraft. Ein Portfolio aus den übrigen, opportunistischen Geschäften erzielte wertgewichtet 82 Basispunkte Überrendite pro Monat. Das ist US-Evidenz aus einem Zeitraum vor der Veröffentlichung und unterliegt dem Abschlag aus Abschnitt 1, Nr. 13.

**Regeln des Insider-Moduls**

1. Nur Käufe am offenen Markt zählen als positives Signal. In US-Daten (Form 4) ist das Transaktionscode P. Zuteilungen (A), Optionsausübungen (M), Steuereinbehalte (F) und Schenkungen (G) werden ignoriert.
2. Verkäufe sind schwache Signale, weil sie oft privat motiviert sind. Gewertet werden nur opportunistische Verkäufe mehrerer Insider innerhalb kurzer Zeit.
3. Geschäfte unter einem vorab festgelegten Handelsplan (US Rule 10b5-1, seit 2023 im Form 4 gekennzeichnet) gelten als routinemäßig.
4. Klassifikation routinemäßig oder opportunistisch je Person nach der Definition oben. Mit weniger als drei Jahren Historie gilt die Person als "unklar" mit halbem Gewicht.
5. Cluster-Kauf, wenn mindestens 3 verschiedene Führungspersonen innerhalb von 60 Tagen kaufen. Cluster wiegen doppelt.
6. Rollengewicht. Vorstandsvorsitz und Finanzvorstand 1,0, übrige Vorstände 0,8, Aufsichtsrat 0,6, eng verbundene Personen 0,5.
7. Größe relativ zum Marktwert der Firma ist wenig aussagekräftig. Relevanter ist die Größe relativ zum bisherigen Eigenbestand der Person, soweit bekannt.
8. Zeitliches Abklingen mit Halbwertszeit 90 Tage.
9. Länderspezifische Meldeschwellen aus `config/insider_thresholds.yaml` (Deutschland 50.000 EUR ab 2026, EU-Standard 20.000 EUR, abweichende nationale Werte pflegen).
10. Das Insider-Signal darf höchstens 15 Prozent des Gesamtwerts ausmachen (`insider_max_weight`). Es kann eine fundamental schwache Aktie nicht in die Kaufliste heben.

### 3.9 Warnsignale (Red Flags)

Jedes Warnsignal hat Schweregrad (info, warnung, stopp) und Belegstelle.

| Warnsignal | Prüfung | Schweregrad |
|---|---|---|
| Going-Concern-Hinweis | Text im Bestätigungsvermerk | stopp |
| Prüferwechsel ohne Ausschreibungsturnus | Vergleich Prüfer Vorjahr | warnung |
| Verspätete Berichtsabgabe | Einreichungsdatum gegen Frist | warnung |
| Beneish über minus 1,78 | Formel | warnung, Eskalation |
| Forderungen wachsen dauerhaft schneller als Umsatz | DSRI über 3 Jahre | warnung |
| Vorräte wachsen dauerhaft schneller als Umsatz | Vorratsreichweite | warnung |
| FCF-Konversion 3 Jahre unter 0,6 | Formel | warnung |
| Verwässerung über 3 Prozent pro Jahr | share_count_change | warnung |
| Hohe Abhängigkeit von Kapitalaktivierung | aktivierte Entwicklungskosten / Umsatz steigt | info |
| Zinsdeckung unter 2 | Formel | stopp für Kauf, Verkaufsprüfung bei Bestand |
| Leerverkäufer-Bericht oder Ermittlungen | Nachrichtenlage, nur mit Quelle | Eskalation an Luca |
| Restatement früherer Jahre | Datenqualitätsprüfung 7 | warnung |
| Wesentliche Geschäfte mit nahestehenden Personen | Anhang | info oder warnung |

### 3.10 Portfolio-Passung

1. Durchschau-Gewichte. Für jeden ETF und Fonds im Bestand werden die Positionsdateien der Emittenten geladen (zum Beispiel iShares-CSV). Daraus entsteht das bestehende Gewicht jeder Aktie im Gesamtvermögen.
2. Diversifikationsbeitrag. Für jeden Kandidaten rechnet das System, wie sich Länder-, Branchen- und Währungsgewichte und das Gewicht der zehn größten Einzelrisiken verändern, wenn die vorgeschlagene Position dazukommt.
3. Lücken im ETF-Bestand. Ein MSCI-World-Portfolio enthält keine Schwellenländer und keine Small Caps. Ob Einzeltitel diese Lücken gezielt füllen sollen, ist eine Entscheidung von Luca (`fill_gaps_preference`, Default `neutral`).
4. Korrelation. Tägliche Renditen der letzten 3 Jahre gegen bestehende Einzeltitel. Neue Kandidaten mit Korrelation über 0,8 zu einer bestehenden Position bekommen einen Abschlag.
5. Positionsgrößen. Gleichgewichtung als Ausgangspunkt, angepasst um Überzeugungsstufe (A, B, C mit Faktoren 1,25 / 1,0 / 0,75). Höchstgewicht je Einzeltitel nach Risikoklasse (6.4), gemessen am Gesamtvermögen einschließlich Durchschau-Gewicht (`max_position_total`). Dazu die Liquiditätsgrenze je Order aus 3.1. Höchstgewicht je Branche im Einzeltitelteil 25 Prozent. Mindestens 10 Einzeltitel, bevor der Einzeltitelanteil 15 Prozent des Gesamtvermögens überschreitet.
6. Kein Kelly-Kriterium und keine Mittelwert-Varianz-Optimierung in v1. Beide reagieren extrem auf Schätzfehler in den erwarteten Renditen.
7. Steuern als Information. Bei Verkaufsprüfungen zeigt das System den realisierten Gewinn, den Sparerpauschbetrag als Konfigurationswert und den Hinweis auf Quellensteuer bei ausländischen Dividenden. Für Aktienverluste existiert in Deutschland ein eigener Verlustverrechnungstopf. Steuerregeln werden vor jeder Verkaufsempfehlung als "bitte aktuell prüfen" markiert, weil das System keine Steuerberatung leistet.

### 3.11 Sektorabhängige Scorecards

Standardkennzahlen wie EV/EBIT oder Nettoverschuldung zu EBITDA sind bei Banken, Versicherern und Immobiliengesellschaften sinnlos, weil Schulden dort Rohstoff des Geschäfts sind. Damit alle Unternehmen bewertet werden können, hat jede Unternehmensart eine eigene Scorecard mit eigenen Kennzahlen, eigenen Säulengewichten und eigenem Bewertungsverfahren. Die Zuordnung steht in `config/scorecards.yaml` (Regeln auf SIC- und NACE-Codes plus Kennzahlenregeln). Ein Agent darf eine andere Zuordnung vorschlagen, wirksam wird sie erst nach Lucas Bestätigung.

| Scorecard | Zuordnung | Kernkennzahlen | Bewertungsverfahren | Grundlage |
|---|---|---|---|---|
| Standard | alle übrigen operativen Unternehmen | Katalog aus 3.3, Scores aus 3.5 | Reverse-DCF, DCF-Szenarien, EV/EBIT, FCF-Rendite | Nissim und Penman (2001), Penman (Financial Statement Analysis and Security Valuation) |
| Wachstum ohne Gewinn | EBIT in den letzten 2 Jahren negativ und Umsatzwachstum über 15 Prozent | Mohanram G-Score (8 Signale relativ zum Branchenmedian. ROA, operativer Cashflow zu Bilanzsumme, operativer Cashflow größer Ergebnis, geringe Volatilität von Ergebnis und Umsatzwachstum, F&E-, Investitions- und Werbeintensität), Bruttomarge, Liquiditätsreichweite in Monaten, Verwässerung | EV/Umsatz gegen Wachstum, Reverse-DCF | Mohanram (2005, Review of Accounting Studies) |
| Banken | SIC 6020 bis 6099, NACE K64.1 | CET1-Quote, Rendite auf materielles Eigenkapital (ROTE), Kosten-Ertrags-Verhältnis, Quote notleidender Kredite, Risikovorsorge zu Krediten, Einlagenanteil an der Refinanzierung | Kurs zu materiellem Buchwert gegen ROTE minus Eigenkapitalkosten (Residualgewinnlogik). Keine EV-Kennzahlen | Calomiris und Nissim (2014, Journal of Financial Intermediation), Damodaran zu Finanzdienstleistern |
| Versicherer | SIC 6300 bis 6411, NACE K65 | Schaden-Kosten-Quote (Combined Ratio) bei Schaden und Unfall, Solvency-II-Quote in der EU bzw. RBC-Quote in den USA, ROE, Reserveabwicklung, Kapitalanlagerendite | Kurs-Buchwert gegen ROE, Dividendenbarwert | Nissim (2010, "Analysis and Valuation of Insurance Companies", Columbia CEASA) |
| Immobilien und REITs | SIC 6798, 6500 bis 6553, NACE L68 | FFO bzw. EPRA-Ergebnis je Aktie, Beleihungsquote (LTV), Zinsdeckung, Restlaufzeit der Schulden, Leerstand | Kurs zu EPRA NTA bzw. NAV, FFO-Rendite. Fair-Value-Gewinne aus IAS 40 bleiben aus dem Ergebnis | EPRA Best Practices Recommendations |
| Versorger und Netze | SIC 4900 bis 4991, NACE D35 | Nettoverschuldung zu EBITDA, regulierte Kapitalbasis, Investitionsquote, Dividendendeckung | EV/EBITDA, Dividendenrendite gegen Deckung | Standard-DCF mit regulierter Rendite |
| Rohstoffe und Zykliker | SIC 1000 bis 1499, 2800 bis 2899, 3310 bis 3399, 3711 bis 3716 und Halbleiter 3674 | Normalisiertes EBIT über 7 bis 10 Jahre, Bilanzstärke im Abschwung | `ev_ebit_normalized` | Zyklusbereinigung wie in 3.4 |
| Holdings und Beteiligungsgesellschaften | Regel, wenn Beteiligungsbuchwerte über 50 Prozent der Bilanzsumme | Summe der Teile, Abschlag auf den Nettoinventarwert | NAV-Abschlag gegen eigene Historie | |

Jede Scorecard hat einen vollständigen Satz an Säulen nach Abschnitt 6.2, damit Noten über Scorecards hinweg dieselbe Bedeutung haben. Verglichen wird trotzdem nur innerhalb einer Scorecard.

Kategorien und Noten sind in Abschnitt 6 definiert.

---

## 4. Unterschiede in der Rechnungslegung

### 4.1 Warum das System normalisiert

Zwei gleich benannte Kennzahlen aus verschiedenen Standards messen oft Verschiedenes. Die Forschung zeigt außerdem, dass derselbe Standard je nach Land unterschiedlich angewandt wird.

| Befund | Quelle | Folgerung |
|---|---|---|
| IFRS-Einführung bedeutet keine einheitliche Praxis. Anreize der Unternehmen und Durchsetzung im Land bestimmen die tatsächliche Bilanzierung | Ball (2006, Accounting and Business Research) | Standardname allein reicht nicht für Vergleichbarkeit |
| Ergebnisglättung und Bilanzpolitik sind in Ländern mit schwachem Anlegerschutz systematisch stärker | Leuz, Nanda und Wysocki (2003, Journal of Financial Economics) | Landesumfeld als Information im Bericht |
| Kapitalmarkteffekte der verpflichtenden IFRS-Einführung zeigen sich vor allem dort, wo Durchsetzung stark ist | Daske, Hail, Leuz und Verdi (2008, Journal of Accounting Research) | Konfidenz hängt nicht nur am Standard |
| Unternehmen mit IAS/IFRS zeigen weniger Ergebnisglättung und zeitnähere Verlustausweise als unter lokalen Standards | Barth, Landsman und Lang (2008, Journal of Accounting Research) | IFRS und US-GAAP als Kernstandards, lokale Standards mit Abschlag |
| Umformulierung der Abschlüsse in operative und finanzielle Teile macht Unternehmen über Standards hinweg vergleichbar | Nissim und Penman (2001), Penman (Lehrbuch) | Das System rechnet Zwischensummen selbst aus Komponenten |
| Aktivierte F&E-Ausgaben sind wertrelevant | Lev und Sougiannis (1996, Journal of Accounting and Economics) | Beide Varianten (aktiviert und aufwandswirksam) ausweisen |

### 4.2 Unterstützte Standards

IFRS (in der EU übernommene Fassung) und US-GAAP werden vollständig normalisiert. Lokale Standards (HGB, J-GAAP, Ind AS, Swiss GAAP FER, chinesische ASBE und andere) werden mit den verfügbaren Daten bewertet, ohne Normalisierung der Punkte aus 4.3, und erhalten höchstens Konfidenz K3. Der Standard steht an jedem Wert (HR-12).

### 4.3 Normalisierungsregeln

Jede Regel ist ein Eintrag in `config/accounting_adjustments.yaml` mit ID, Version und Quelle. Jede angewandte Anpassung erscheint mit Betrag im Berichtsabschnitt 8 der Analyse (Abschnitt 12.3).

| ID | Thema | IFRS | US-GAAP | Regel im System |
|---|---|---|---|---|
| ACC-01 | Leasing | IFRS 16, fast alle Leasingverhältnisse in der Bilanz, Aufwand als Abschreibung und Zins, EBITDA dadurch höher | ASC 842, Operating Leases in der Bilanz, Aufwand linear im operativen Ergebnis | Basis "nach Leasing" ist Standard. Leasingverbindlichkeiten zählen immer zur Nettoverschuldung. Für US-GAAP-Operating-Leases wird der Leasingaufwand aus dem Anhang zum EBITDA addiert, damit Zähler und Nenner von EV/EBITDA konsistent sind. Zusätzlich wird eine Basis "vor Leasing" gespeichert |
| ACC-02 | Entwicklungskosten | IAS 38, Aktivierung bei erfüllten Kriterien | ASC 730, sofort Aufwand (Ausnahme Software) | Vergleichsbasis "voll aufwandswirksam". Aktivierte Entwicklungskosten der Periode werden als Aufwand gebucht, die Abschreibung darauf zurückgerechnet. Beide EBIT-Varianten werden gespeichert |
| ACC-03 | Vorräte | LIFO verboten | LIFO erlaubt | LIFO-Reserve aus dem Anhang zu den Vorräten addieren, Veränderung der Reserve im Materialaufwand korrigieren |
| ACC-04 | Zinsen und Dividenden in der Kapitalflussrechnung | Bis Geschäftsjahr 2026 Wahlrecht. Ab IFRS 18 (Geschäftsjahre ab 1.1.2027) gezahlte Zinsen und Dividenden unter Finanzierung, erhaltene grundsätzlich unter Investition | Gezahlte Zinsen im operativen Cashflow | Einheitliche FCF-Definition. Gezahlte Zinsen werden immer vom operativen Cashflow abgezogen, wenn sie unter Finanzierung ausgewiesen sind. Die FCFF-Variante addiert Zinsen nach Steuern zurück |
| ACC-05 | Ergebnis-Zwischensummen | Ab IFRS 18 Pflichtsumme "operatives Ergebnis" nach eigener Abgrenzung | Keine einheitliche EBIT-Definition | Das System berechnet EBIT selbst aus Komponenten nach Registerformel und übernimmt keine ausgewiesene Zwischensumme ungeprüft |
| ACC-06 | Bereinigte Kennzahlen des Managements | Ab IFRS 18 Anhangangabe mit Überleitung für managementdefinierte Kennzahlen | SEC Regulation G verlangt Überleitung | Bereinigte Werte sind nie Primärwert. Ein dauerhafter Abstand über 20 Prozent zwischen bereinigt und unbereinigt ist Ungereimtheit INC-05 |
| ACC-07 | Wertaufholung | erlaubt außer bei Goodwill | verboten | Wertaufholungen als Sondereffekt, nicht im normalisierten EBIT |
| ACC-08 | Neubewertung | IAS 16 Neubewertungsmodell, IAS 40 Fair Value mit Erfolgswirkung | Anschaffungskosten | Fair-Value-Änderungen aus dem operativen Ergebnis entfernen |
| ACC-09 | Goodwill | keine planmäßige Abschreibung | keine planmäßige Abschreibung bei Börsennotierten | Bei HGB planmäßige Abschreibung für den Vergleich zurückrechnen. Goodwill-Anteil am Eigenkapital ausweisen |
| ACC-10 | Pensionen | IAS 19, Neubewertungen im OCI, Nettozins im Finanzergebnis | ASC 715, Teile können im operativen Ergebnis stehen | Dienstzeitaufwand operativ, Zinsanteil Finanzierung, Defizit als schuldenähnlicher Posten (`net_debt_incl_pensions`) |
| ACC-11 | Aktienbasierte Vergütung | IFRS 2 | ASC 718 | Immer Aufwand, auch wenn das Management sie herausrechnet |
| ACC-12 | Versicherungsverträge | IFRS 17 seit 2023 | LDTI seit 2023 | Nur innerhalb desselben Standards vergleichen. Zeitreihen vor und nach der Umstellung trennen |
| ACC-13 | Geschäftsjahr | beliebiger Stichtag | beliebiger Stichtag | Für Vergleichsgruppen Kalendarisierung auf einen gemeinsamen Stichtag aus Quartalswerten (TTM). Bei Halbjahresberichtern zeitanteilig mit Konfidenzabschlag |
| ACC-14 | Minderheitsanteile | Ausweis im Eigenkapital | Ausweis im Eigenkapital | Minderheiten zählen zum Unternehmenswert. Kennzahlen je Aktie nur mit dem Ergebnis der Aktionäre des Mutterunternehmens |

### 4.4 Umstellungen und Zeitreihenbrüche

Bei Standardwechseln (IFRS 16 ab 2019, IFRS 17 ab 2023, IFRS 18 ab 2027) markiert das System den Bruch in der Zeitreihe. Trends werden nur über vergleichbare Perioden gerechnet. Liefert der neue Bericht angepasste Vorjahreszahlen, werden diese als eigene Fassung gespeichert (siehe Restatements in 3.2).

### 4.5 Landesumfeld

Das Land der Notierung und des Sitzes wird mit der Einordnung nach Leuz, Nanda und Wysocki als Information im Bericht angezeigt. Es fließt nicht in die Note ein, weil die Einordnung auf älteren Daten beruht. Beneish-Score und Accruals (3.5) messen die Bilanzqualität des einzelnen Unternehmens direkt.

---

## 5. Währungen

### 5.1 Grundlagen

| Befund | Quelle | Folgerung |
|---|---|---|
| Währungsrisiko eines Unternehmens ist die Empfindlichkeit seines Werts gegenüber Wechselkursen und hängt davon ab, wo Umsätze und Kosten anfallen, nicht von der Notierungswährung | Adler und Dumas (1984, Financial Management) | Exposure wird aus der regionalen Umsatzverteilung bestimmt |
| Wechselkurseffekte auf Unternehmenswerte sind messbar, werden vom Markt aber teils verzögert eingepreist | Jorion (1990, Journal of Business), Bartov und Bodnar (1994, Journal of Finance) | Wachstum in konstanter Währung getrennt ausweisen |
| Umrechnung nach Stichtagskurs für Bilanzposten und Durchschnittskurs für Erfolgsgrößen | IAS 21, ASC 830 | System übernimmt dieselbe Logik |
| Cashflows und Diskontsatz müssen in derselben Währung stehen. Umrechnung von Kapitalkosten über die Inflationsdifferenz | Damodaran (Investment Valuation), Fisher-Beziehung | DCF immer in Berichtswährung |
| Hochinflationsländer erfordern Indexierung der Abschlüsse | IAS 29 | Eigener Flag und Konfidenzabschlag |

### 5.2 Regeln

1. Jeder Wert wird in Originalwährung gespeichert. Umrechnungskurse liegen separat mit Datum und Quelle (EZB-Referenzkurse).
2. Verhältniskennzahlen (Margen, Renditen, Quoten) werden in Berichtswährung gerechnet und sind damit währungsneutral.
3. Bilanzposten werden zum Stichtagskurs umgerechnet, GuV- und Cashflow-Posten zum Durchschnittskurs der Periode. Der Durchschnitt entsteht aus täglichen Referenzkursen.
4. Marktkapitalisierung entsteht in Kurswährung. Für den Unternehmenswert wird die Nettoverschuldung aus der Berichtswährung zum aktuellen Kassakurs in die Kurswährung umgerechnet. Für Multiples wird die TTM-Stromgröße zum Durchschnittskurs der letzten vier Quartale umgerechnet. Kurs- und Berichtswährung weichen häufig voneinander ab, etwa wenn ein Unternehmen in USD berichtet und in EUR oder GBP notiert.
5. Wachstum wird dreifach ausgewiesen. In Berichtswährung (geht in die Note ein, weil sie die wirtschaftliche Leistung zeigt), in EUR (zeigt Lucas Erleben als EUR-Anleger) und in konstanter Währung, sofern der Bericht diese Angabe mit Beleg liefert.
6. DCF und Reverse-DCF laufen in Berichtswährung mit dem risikofreien Zins derselben Währung. Der Wert je Aktie wird zum Kassakurs in EUR umgerechnet. Liegen Annahmen in einer anderen Währung vor, wird der Diskontsatz über die Fisher-Beziehung umgerechnet. (1 + r_A) = (1 + r_B) mal (1 + π_A) / (1 + π_B), mit π als erwarteter Inflation.
7. Das Endwachstum im DCF liegt höchstens beim langfristigen nominalen risikofreien Zins der Berichtswährung.
8. Hochinflationsländer nach IAS 29 stehen in `config/hyperinflation.yaml`. Betroffene Unternehmen erhalten den Flag `hyperinflation`, höchstens Konfidenz K3, und Zeitreihen werden real betrachtet.
9. Ökonomisches Währungsexposure. Die geografische Umsatzverteilung aus dem Segmentbericht ergibt einen Umsatzwährungsmix. Auf Portfolioebene zeigt das Dashboard getrennt die Notierungswährungen und die ökonomische Umsatzherkunft, jeweils einschließlich Durchschau auf die ETFs.
10. Unterwährungen werden erkannt und umgerechnet. GBX (Pence) gegen GBP, ZAc gegen ZAR, ILA gegen ILS. Ein Faktor-100-Fehler ist der häufigste Datenfehler bei britischen Werten.
11. ADR und GDR werden über das Depotverhältnis auf die Stammaktie normiert, damit Kennzahlen je Aktie stimmen.
12. Quellensteuer auf Dividenden je Land steht in `config/withholding_tax.yaml` und erscheint im Bericht als Information.
13. Plausibilitätsprüfung INC-13. Der aus zwei Notierungen abgeleitete Wechselkurs (Kurs in EUR geteilt durch Kurs in Heimatwährung) darf höchstens 2 Prozent vom Referenzkurs abweichen. Sonst liegt ein Daten- oder Einheitenfehler vor.

---

## 6. Bewertungsskala

### 6.1 Drei getrennte Achsen

Jedes Unternehmen erhält drei Angaben, die immer zusammen angezeigt werden, etwa "B · K2 · R3".

| Achse | Frage | Werte |
|---|---|---|
| Note | Wie attraktiv ist das Unternehmen im Vergleich zu seiner Vergleichsgruppe, gemessen an Qualität, Bewertung, Stabilität, Wachstum, Kapitalallokation und Insider-Verhalten? | A bis E, dazu N für "nicht bewertbar" |
| Konfidenz | Wie belastbar ist diese Note? | K1 bis K4 |
| Risiko | Wie stark kann der Kurs schwanken und wie schwer ist die Position zu handeln? | R1 bis R5 |

Die Trennung ist Absicht. Eine gute Note auf dünner Datenbasis ist eine andere Aussage als dieselbe Note auf geprüfter Datenbasis. Wer beides zu einer Zahl verrechnet, versteckt die Unsicherheit. Risiko fließt nicht in die Note ein, weil die Forschung zu niedrig volatilen Aktien (Ang, Hodrick, Xing und Zhang 2006, Journal of Finance. Frazzini und Pedersen 2014, Journal of Financial Economics) keinen verlässlichen Renditeaufschlag für höheres Risiko findet. Risiko steuert stattdessen die Positionsgröße.

### 6.2 Note

**Säulen und Default-Gewichte (Scorecard Standard)**

| Säule | Gewicht | Kennzahlen (Auswahl, vollständig im Register) |
|---|---|---|
| Qualität | 25 % | gp_to_assets, roic, fcf_margin, Margenstabilität, Piotroski F |
| Bewertung | 25 % | ev_ebit, fcf_yield, Abstand implizites Wachstum zur Historie, Sicherheitsmarge |
| Finanzielle Stabilität | 15 % | net_debt_to_ebitda, interest_coverage, Altman-Zone, debt_maturity_12m |
| Wachstum und Trend | 15 % | revenue_cagr_5y, fcf_per_share_cagr_5y, Theil-Sen-Steigung der Kernkennzahlen |
| Kapitalallokation | 10 % | shareholder_yield, share_count_change_3y, acquisition_intensity, ROIC auf Zuwachs |
| Insider | 10 % (höchstens 15 %) | Signal aus 3.8. Ohne Insider-Daten wird das Gewicht auf die anderen Säulen verteilt |

Die anderen Scorecards nutzen dieselben sechs Säulen mit eigenen Kennzahlen und Gewichten in `config/scorecards.yaml`. Banken bewerten etwa unter "Finanzielle Stabilität" die CET1-Quote und unter "Qualität" die ROTE.

**Rechenweg**

1. Jede Kennzahl wird in ein Perzentil (0 bis 100) innerhalb der Vergleichsgruppe zum Analysedatum umgerechnet. Vergleichsgruppe ist dieselbe Scorecard, dieselbe Branche und dieselbe Region (Europa, Nordamerika, Asien-Pazifik, Schwellenländer). Hat sie weniger als 15 Mitglieder, wird stufenweise erweitert (Branche global, dann Scorecard in der Region, dann Scorecard global). Die genutzte Stufe steht im Bericht.
2. Rangbasierte Standardisierung ist robust gegen Ausreißer und unabhängig von Einheit und Währung. Sie ist in der Faktorforschung üblich, etwa bei Asness, Frazzini und Pedersen ("Quality Minus Junk", 2019) und Asness, Moskowitz und Pedersen ("Value and Momentum Everywhere", 2013, Journal of Finance).
3. Die Richtung jeder Kennzahl steht im Register (höher ist besser, niedriger ist besser oder Zielband, etwa beim Current Ratio).
4. Säulenwert ist der Mittelwert der Kennzahl-Perzentile der Säule. Fehlende Kennzahlen werden nicht geschätzt (HR-05). Die Gewichte innerhalb der Säule werden auf die vorhandenen Kennzahlen verteilt.
5. Gesamtwert ist der gewichtete Mittelwert der Säulen.
6. Absolute Kappungsgrenzen, weil Perzentile relativ sind und in einer schwachen Vergleichsgruppe auch der Beste schwach sein kann.

| Bedingung | Höchstwert |
|---|---|
| Stopp-Flag aus 3.9 | 49 (D) |
| Altman Z in der Gefahrenzone (Scorecard Standard) | 64 (C) |
| FCF in drei Jahren negativ und Nettoverschuldung über dem Vierfachen des EBITDA | 49 (D) |
| Abdeckung unter 70 Prozent der gewichteten Kennzahlen | 64 (C) |
| Beneish über Schwelle ohne Entkräftung durch F1 | 64 (C) |

7. Umrechnung in die Note.

| Note | Wert | Bedeutung |
|---|---|---|
| A | 80 bis 100 | sehr attraktiv im Vergleich zur Gruppe |
| B | 65 bis 79 | attraktiv |
| C | 50 bis 64 | neutral |
| D | 35 bis 49 | unattraktiv |
| E | 0 bis 34 | meiden |
| N | | nicht bewertbar, Grund angegeben |

Die Note ist ein relativer Rang und keine Renditeprognose (siehe McLean und Pontiff in Abschnitt 1).

### 6.3 Konfidenz

| Stufe | Bedingungen (alle müssen erfüllt sein) |
|---|---|
| K1 sehr belastbar | Primärquelle XBRL oder doppelt geprüfte Extraktion, Quellenabgleich bestanden, mindestens 8 Jahre Historie, Abdeckung mindestens 90 Prozent, IFRS oder US-GAAP, Größenklasse Small oder größer, Tiefenanalyse mit Status `verified` |
| K2 belastbar | Quellenabgleich bestanden, mindestens 5 Jahre Historie, Abdeckung mindestens 80 Prozent, IFRS oder US-GAAP, Größenklasse Small oder größer. Ohne Tiefenanalyse ist K2 die beste erreichbare Stufe |
| K3 eingeschränkt | mindestens 3 Jahre Historie und Abdeckung mindestens 70 Prozent. Typisch für lokale Standards, nur eine Datenquelle, Micro- und Nano-Caps, Hochinflation |
| K4 schwach | alles darunter. Die Note wird grau angezeigt und erscheint nie in den oberen Ranglisten |

### 6.4 Risikoklasse

Eingänge sind die annualisierte Volatilität der Tagesrenditen in EUR über 3 Jahre, der größte Kursrückgang über 5 Jahre, die Verschuldung (scorecardspezifisch), die Amihud-Illiquidität, die Größenklasse und die Volatilität des operativen Ergebnisses. Jeder Eingang wird in ein Quintil des Gesamtuniversums eingeordnet (1 bis 5). Die Risikoklasse ist der gerundete Mittelwert, R1 sehr niedrig bis R5 sehr hoch.

Die Risikoklasse begrenzt die Positionsgröße (Default, in Prozent des Gesamtvermögens einschließlich Durchschau). R1 und R2 5 Prozent, R3 4 Prozent, R4 3 Prozent, R5 2 Prozent.

### 6.5 Entscheidungskategorien

| Kategorie | Bedingung |
|---|---|
| Kaufkandidat | Note A oder B, Konfidenz K1 oder K2, alle Prüfebenen bestanden, keine Stopp-Flags, Sicherheitsmarge aus 3.6 erfüllt, Hysterese aus 9.5 erfüllt |
| Beobachten | Note B mit zu hoher Bewertung, Note C mit Aufwärtstrend oder Note A mit K3 |
| Halten | Bestand, Ergebnis der Bestandsprüfung (Abschnitt 10) |
| Teilverkauf prüfen, Verkauf prüfen, Tausch prüfen | Bestand, nur aus Abschnitt 10 |
| Eskaliert | Prüfung nicht bestanden oder Jury uneinig, wartet auf Luca |
| Nicht bewertbar | Status N mit Grund |

Alle Schwellen sind Defaults in `config/scoring.yaml`. Sie werden nach der Papierdepot-Phase überprüft, aber nie an dem Zeitraum angepasst, auf dem sie getestet werden.

### 6.6 Kalibrierung der Skala

Nach 24 Monaten Papierdepot prüft das System, ob die Noten die Folgeentwicklung ordnen. Gemessen wird die Rangkorrelation (Spearman) zwischen Note und Rendite der folgenden 12 Monate sowie die Rendite je Notenstufe. Ist die Ordnung nicht monoton (A besser als B besser als C), wird die Gewichtung in einem getrennten Zeitraum neu geprüft und die Änderung als neue Methodik-Version eingeführt.

### 6.7 Darstellung

Die Note erscheint als Buchstabe in einem farbigen Kästchen, die Konfidenz als Füllstand mit vier Segmenten, die Risikoklasse als Ziffer. Farbe trägt nie allein die Bedeutung. Jede Note ist anklickbar und zeigt die Zerlegung in Säulen und Kennzahl-Perzentile samt Vergleichsgruppe.

---

---

## 7. Datenquellen und Datenschicht

### 7.1 Handelsuniversum

Trade Republic veröffentlicht keine maschinenlesbare Instrumentenliste. Das System nimmt deshalb alle Aktien auf, die an deutschen Börsenplätzen handelbar sind, und ergänzt breite Indexbestände. Damit deckt es das Angebot von Trade Republic weitgehend ab, ohne auf eine inoffizielle Schnittstelle angewiesen zu sein.

| Schritt | Quelle | Häufigkeit |
|---|---|---|
| Basisuniversum | Listen handelbarer Instrumente, die die Deutsche Börse für Xetra und Börse Frankfurt als CSV veröffentlicht, gefiltert auf Aktien (Dateinamen und Format in Phase 5 prüfen) | wöchentlich |
| Ergänzung | Positionsdateien breiter ETFs (etwa MSCI ACWI IMI), Indexbestandteile DAX, MDAX, SDAX, TecDAX | monatlich |
| Kennungen | ISIN, LEI (GLEIF-API, kostenlos), Ticker, CIK bei US-Emittenten (SEC `company_tickers.json`) | monatlich |
| Zusammenführung | Mehrfachlistings auf LEI, Primärnotierung als Kursquelle | je Aktualisierung |
| Handelbarkeit bei Trade Republic | Bestätigung durch Luca in der App für Kaufkandidaten, optional `pytr` im Nur-Lese-Modus (inoffiziell, standardmäßig aus) | je Kaufkandidat |

Das Universum umfasst über 10.000 Aktien. Alle erhalten bei jedem Lauf eine quantitative Note ohne Modellaufrufe. Für US-Emittenten und EU-Emittenten an regulierten Märkten liegen strukturierte Daten kostenlos vor. Für die übrigen Unternehmen (Freiverkehr, Asien, Schwellenländer) stammen die Daten vom kommerziellen Anbieter aus 7.2. Sie erhalten meist Konfidenz K3, weil die zweite Quelle für den Abgleich fehlt. Welche Unternehmen eine Tiefenanalyse bekommen, bestimmt die Kategorie-Abfrage (9.8).

### 7.2 Abschlussdaten

| Region | Primärquelle | Format | Kosten | Hinweise |
|---|---|---|---|---|
| USA | SEC EDGAR, `data.sec.gov` (Company Facts, Company Concept, Frames, Submissions) | JSON mit US-GAAP-XBRL-Konzepten | kostenlos | Pflicht-Header `User-Agent` mit Name und E-Mail, höchstens 10 Anfragen pro Sekunde. Bibliothek `edgartools` nutzen |
| EU, regulierte Märkte | ESEF-Inline-XBRL über `filings.xbrl.org` (XBRL International), Python-Paket `xbrl-filings-api` | xBRL-JSON, Bericht als XHTML | kostenlos | Abdeckung ab Geschäftsjahr 2020, nicht vollständig. Freiverkehrswerte fehlen, weil dort keine ESEF-Pflicht gilt |
| EU, Rückfall | Unternehmensregister und Investor-Relations-Seiten | PDF | kostenlos | Extraktion nach Abschnitt 7.4 |
| EU, mittelfristig | ESAP (European Single Access Point), Aufbau läuft | | | Bei Verfügbarkeit als Primärquelle einbinden |
| Querprüfung | Ein kommerzieller Anbieter, zum Beispiel Financial Modeling Prep, EODHD oder financialreports.eu | REST-JSON | ab rund 20 bis 50 EUR pro Monat | Dient als zweite Quelle für die Datenqualitätsprüfung 5 und für Zeitreihen vor 2020 |

ESEF-Taxonomie und US-GAAP-Taxonomie haben unterschiedliche Konzeptnamen. Das Mapping auf die internen Kennzahl-Eingaben steht in `config/concept_map.yaml` mit Vorrangreihenfolge je interner Größe. Fehlt ein Konzept, sucht der Extraktionsagent im Bericht und kennzeichnet den Wert als `source_type: pdf_extracted`.

### 7.3 Markt- und Zusatzdaten

| Daten | Quelle | Hinweise |
|---|---|---|
| Kurse und Volumen (täglich) | kommerzieller Anbieter aus 7.2, Rückfall `yfinance` nur für Entwicklung | `yfinance` ist inoffiziell und für den Dauerbetrieb ungeeignet |
| Wechselkurse | EZB-Referenzkurse (SDMX-API) | alle Vergleiche in EUR, Originalwährung immer mitspeichern |
| Risikofreier Zins | Bundesbank-Zinsstrukturkurve, US-Treasury (FRED) | |
| Aktienrisikoprämie, Branchenbetas, Branchenmultiples | Damodaran-Datensätze (NYU Stern, jährlich und monatlich) | als datierter Snapshot speichern |
| Insider Deutschland | BaFin-Datenbank "Geschäfte von Führungskräften" plus Veröffentlichungen der Emittenten | BaFin bietet keine offizielle API. Abruf höflich mit Pausen und Caching, robots.txt beachten. Alternativ kommerzieller Insider-Feed |
| Insider USA | SEC Form 4 (XML) über EDGAR | strukturiert, Transaktionscodes direkt nutzbar |
| Insider übrige EU | Seiten der nationalen Aufsichten | v2 |
| ETF-Bestände | Positionsdateien der ETF-Emittenten | für Durchschau-Gewichte |
| Nachrichten | nur über Websuche des Agenten mit Quellen-URL | nie als Zahlenquelle |

### 7.4 PDF-Extraktion (nur Rückfall)

1. Parser in dieser Reihenfolge. Docling (Open Source, lokal) zuerst, bei schlechter Tabellenqualität LlamaParse. Beide liefern Seitenzahlen und Tabellenstruktur.
2. Der Extraktionsagent bekommt die relevanten Seiten vollständig in den Kontext, statt Schnipsel aus einer Vektorsuche. Die FinanceBench-Ergebnisse sprechen klar für langen Kontext statt Retrieval.
3. Jeder extrahierte Wert speichert Dokument-Hash, Seite, Tabellenüberschrift, Zeilen- und Spaltenbeschriftung, Einheit, Skalierung und den Originaltext der Zelle.
4. Zwei unabhängige Extraktionen (unterschiedliche Prompts, idealerweise unterschiedliche Modelle). Weichen sie ab, entscheidet der Zahlenprüfer anhand der Seite.
5. Extrahierte Werte durchlaufen dieselben Datenqualitätsprüfungen wie XBRL-Werte.

### 7.5 Zeitpunktbezug (Point-in-Time)

Jeder Datensatz hat drei Zeitstempel.

| Feld | Bedeutung |
|---|---|
| `period_end` | Stichtag, auf den sich der Wert bezieht |
| `published_at` | Zeitpunkt der öffentlichen Verfügbarkeit (Einreichungsdatum, Meldedatum) |
| `retrieved_at` | Abrufzeitpunkt durch das System |

Jede Abfrage für eine Analyse zum Zeitpunkt T filtert auf `published_at <= T`. Bei Restatements gelten bis zum Restatement-Datum die alten Werte. Das ist Voraussetzung für jeden ehrlichen Backtest.

### 7.6 Speicherung

| Ebene | Technik | Inhalt |
|---|---|---|
| Rohdaten | Dateisystem `data/raw/`, Name ist SHA-256 des Inhalts | Originale aller Berichte, JSON-Antworten, Positionsdateien. Unveränderlich |
| Strukturierte Daten | DuckDB (eine Datei, schnelle Analysen) | Tabellen aus Abschnitt 7.7 |
| Lauf-Artefakte | `runs/<run_id>/` | alle Agenten-Ein- und Ausgaben als JSON, Berichte, Diagramme |
| Code und Konfiguration | Git | jede Konfigurationsänderung ist ein Commit |

DuckDB reicht für das Datenvolumen eines Privatanlegers völlig. Ein Wechsel auf PostgreSQL ist nur nötig, wenn mehrere Prozesse gleichzeitig schreiben.

### 7.7 Datenmodell (Kern)

```
issuers(lei PK, name, country, sector_sic, sector_nace, accounting_standard, fiscal_year_end)
listings(isin PK, lei FK, ticker, exchange_mic, currency, is_primary, tr_tradable, tr_checked_at)
documents(doc_hash PK, lei FK, doc_type, period_end, published_at, retrieved_at, source_url, language, pages)
facts(fact_id PK, lei FK, concept, internal_metric, value, unit, scale, currency, period_start, period_end,
      published_at, source_type[xbrl|pdf_extracted|vendor], doc_hash FK, page, xbrl_context, extraction_run_id,
      superseded_by)
prices(isin, date, close, volume, currency, source)
metrics(run_id, lei, metric_id, metric_version, period_end, value, inputs_json, computed_at)
insider_tx(tx_id PK, lei, person_name, role, relation[self|spouse|child|household|controlled_entity],
           tx_type[buy|sell|grant|exercise|tax|gift|other], open_market bool, plan_10b5_1 bool,
           shares, price, currency, value_eur, trade_date, published_at, source_doc_hash, routine_class)
scores(run_id, lei, component, value, percentile, peer_group, methodology_version)
valuations(run_id, lei, method, scenario, assumptions_json, value_per_share, implied_growth, sensitivity_json)
flags(run_id, lei, flag_id, severity, evidence_json)
judgments(run_id, lei, judge_id, model, check_type, verdict, confidence, rationale, evidence_json, blind bool)
decisions(run_id, lei, category, score_total, proposed_weight, conviction, status, human_decision, human_note)
holdings(as_of, account, isin, quantity, value_eur, source)
lookthrough(as_of, isin_underlying, weight_total, via_funds_json)
paper_portfolio(date, isin, weight, entry_price, run_id)
```

---

## 8. Agentenarchitektur

### 8.1 Grundprinzip

Die Architektur trennt drei Arten von Arbeit.

1. Deterministische Pipeline in Python für alles, was eindeutig berechenbar ist (Daten laden, Kennzahlen, Scores, DCF-Rechnung, Portfolio-Mathematik).
2. LLM-Agenten nur dort, wo Lesen, Einordnen und Argumentieren nötig ist (Berichte lesen, Annahmen begründen, Gegenargumente finden, Bericht schreiben).
3. Prüfagenten, die beides kontrollieren.

Das Vorbild aus der Forschung ist TradingAgents (UCLA, MIT, Tauric Research, AAAI 2025). Dort analysieren Fachagenten, ein Bull- und ein Bear-Researcher debattieren, ein Risikoteam prüft und ein Manager entscheidet. Übernommen wird die Rollentrennung und die Debatte. Nicht übernommen wird die Ausrichtung auf kurzfristiges Trading und technische Analyse, die zu einem Anlagehorizont von 15 bis 20 Jahren nicht passt.

Kim, Muhn und Nikolaev (Chicago Booth, 2024) zeigen, dass ein LLM aus standardisierten Abschlüssen die Richtung künftiger Gewinne besser vorhersagt als der Median der Analysten, wenn es per Chain-of-Thought wie ein Analyst vorgeht (Trends erkennen, Kennzahlen rechnen, interpretieren). Das stützt den Einsatz von LLMs für die Einordnung. Die Zahlen selbst rechnet in diesem System trotzdem Python.

### 8.2 Übersicht der Agenten

```
                       ┌────────────────────────┐
                       │  Orchestrator (Haupt-  │
                       │  session / Agent SDK)  │
                       └──────────┬─────────────┘
          ┌───────────────────────┼────────────────────────────┐
   Python-Pipeline         Tiefenanalyse je Kandidat       Portfolio & Bericht
   P1 Universum            A0 Kategorie-Agent             A8 Portfolio-Agent
   P2 Klassifikation       A1 Datenbeschaffung            A10 Bestandsprüfer
   P3 Datenqualität        A2 Extraktion (2x, Rückfall)   A9 Synthese-Agent
   P4 Normalisierung       A3 Fundamentalanalyse          J4 Endkontrolle
   P5 Kennzahlen/Scores    A4 Qualitative Analyse
   P6 Note/Konfidenz/Risiko A5 Bewertung
   G  Gates (12.6) nach jeder Agentenausgabe
                           A6 Insider-Analyse
                           A7 Bear-Agent (Gegenposition)
                           J1 Zahlenprüfer (blind)
                           J2 Belegprüfer (Groundedness)
                           J3 Jury (3 Richter)
                           F1 Forensik (bei Eskalation)
```

### 8.3 Agentenkatalog

Für jeden Agenten gilt dieselbe Struktur. Rolle, Eingabe, Ausgabe (JSON-Schema in `schemas/`), Werkzeuge, Modellklasse, Grenzen. Modellklassen sind Platzhalter in `config/models.yaml` (`fast`, `standard`, `strong`), damit Modellwechsel ohne Codeänderung möglich sind.

**A0 Kategorie-Agent**
- Rolle. Freitext-Themen aus der Kategorie-Abfrage in eine Liste von Unternehmen übersetzen.
- Eingabe. Thema als Text, Größen- und Regionsfilter.
- Ausgabe. `theme_matches[]` mit LEI, Begründung und Belegstelle aus der Geschäftsbeschreibung.
- Werkzeuge. Skript `search_descriptions.py` (Volltextsuche über gespeicherte Geschäftsbeschreibungen und Branchencodes).
- Modell. `standard`.
- Grenzen. Kein Unternehmen aus Vorwissen. Luca bestätigt die Liste.

**A1 Datenbeschaffung**
- Rolle. Fehlende Dokumente finden und ablegen (Geschäftsbericht, Halbjahresbericht, Vergütungsbericht, Proxy, Ad-hoc-Mitteilungen der letzten 12 Monate).
- Eingabe. `lei`, Liste fehlender Dokumenttypen aus P3.
- Ausgabe. `documents_found[]` mit URL, Hash, Typ, Periode.
- Werkzeuge. WebSearch, WebFetch, Skript `fetch_document.py` (lädt, hasht, legt ab).
- Modell. `fast`.
- Grenzen. Darf keine Zahlen liefern. Nur Dokumente von Emittenten, Aufsichtsbehörden und offiziellen Registern.

**A2 Extraktion (zwei Instanzen, nur Rückfall)**
- Rolle. Werte aus PDF-Seiten in das interne Schema übertragen.
- Eingabe. Dokument-Hash, Seitenbereich, Liste gesuchter interner Größen.
- Ausgabe. `extracted_facts[]` mit allen Pflichtfeldern aus 7.4 Punkt 3.
- Werkzeuge. Read, Skript `parse_pdf.py`.
- Modell. Instanz 1 `standard`, Instanz 2 anderes Modell oder anderer Prompt.
- Grenzen. Keine Umrechnungen. Was nicht in der Tabelle steht, bleibt leer.

**A3 Fundamentalanalyse**
- Rolle. Kennzahlen, Trends und Scores aus P4 interpretieren, Treiber erklären, Auffälligkeiten mit Berichtsstellen verknüpfen.
- Eingabe. `metrics`, `scores`, `flags` des Kandidaten, Branchenperzentile, relevante Berichtsseiten.
- Ausgabe. `fundamental_view` mit Thesen, jede These mit Kennzahl-IDs und Belegen, Einschätzung der Ertragsqualität.
- Werkzeuge. Read, Skript `query_metrics.py` (nur lesen).
- Modell. `strong`.
- Grenzen. Darf keine neuen Zahlen einführen. Jede Zahl im Text muss aus `metrics` stammen und wird per ID referenziert.

**A4 Qualitative Analyse**
- Rolle. Themen aus Abschnitt 3.7 bearbeiten, Risikofaktoren mit Vorjahr vergleichen.
- Eingabe. Textteile der aktuellen und vorjährigen Berichte, Vergütungsbericht.
- Ausgabe. `qualitative_view` je Thema mit Befund, Bewertung (positiv, neutral, negativ), Zitat und Seite.
- Werkzeuge. Read, Grep.
- Modell. `strong`.

**A5 Bewertung**
- Rolle. Szenario-Annahmen für den DCF vorschlagen und begründen, Vergleichsgruppe vorschlagen, Ergebnis des Reverse-DCF einordnen.
- Eingabe. Historie, Branchendaten, Ergebnisse von A3 und A4.
- Ausgabe. `valuation_assumptions` je Szenario mit Begründung je Annahme, danach die von Python gerechneten Werte als Anhang.
- Werkzeuge. Skript `run_dcf.py`, `run_reverse_dcf.py`, `peer_multiples.py`.
- Modell. `strong`.
- Grenzen. Base-Szenario-Wachstum über der 10-Jahres-Historie braucht eine ausdrückliche, belegte Begründung, sonst wird gekappt.

**A6 Insider-Analyse**
- Rolle. Ergebnis des deterministischen Insider-Moduls einordnen, auffällige Muster mit Kontext versehen (zum Beispiel Kauf nach Kurseinbruch, Kauf trotz Sperrfrist-Nähe).
- Eingabe. `insider_tx` der letzten 24 Monate, Klassifikation, Kursverlauf, Berichtskalender.
- Ausgabe. `insider_view` mit Signalstärke und Begründung.
- Modell. `standard`.

**A7 Bear-Agent**
- Rolle. Die stärkste begründete Gegenposition formulieren. Ziel ist nicht Ablehnung um jeden Preis, sondern die drei wichtigsten Wege aufzuzeigen, wie die Investition scheitern könnte, inklusive Pre-Mortem ("es ist 2031, die Aktie hat 50 Prozent verloren, warum?").
- Eingabe. Alle Ergebnisse A3 bis A6 plus dieselben Rohdaten.
- Ausgabe. `bear_case` mit Risiken, Eintrittsindikatoren, Belegen und der Frage "was müsste man beobachten, um früh zu merken, dass die These falsch ist?".
- Modell. `strong`, möglichst anderes Modell als A3.
- Ablauf. Danach eine Erwiderungsrunde durch A3 und A5 (höchstens 2 Runden). Ungeklärte Punkte gehen offen in den Bericht.

**A8 Portfolio-Agent**
- Rolle. Ergebnisse des Python-Portfoliomoduls (Abschnitt 3.10) erklären und Gewichtungsvorschlag formulieren.
- Ausgabe. `portfolio_proposal` mit Gewicht, Betrag in EUR, Sparplan-Variante, Begründung, Effekt auf Länder, Branchen, Währung und Top-10-Risiken.
- Modell. `standard`.

**A9 Synthese-Agent**
- Rolle. Entscheidungsvorlage schreiben (Abschnitt 13.2).
- Grenzen. Nur geprüfte Inhalte (Status `verified`). Keine neuen Behauptungen.
- Modell. `strong`.

**A10 Bestandsprüfer**
- Rolle. Ergebnisse der Prüfregeln HOLD-01 bis HOLD-10 erklären, qualitative Thesenpunkte gegen neue Berichte prüfen, Thesenkarten für neue Käufe entwerfen.
- Eingabe. Thesenkarte, aktuelle Analyse, Ergebnisse aus `core/holdings_review.py`, Steuerrechnung.
- Ausgabe. `holding_review` je Position mit Ergebnisstufe aus 10.5, Begründung, Belegen und Umkehrbedingung.
- Modell. `strong`.
- Grenzen. Kann nur abwerten oder eskalieren (HR-13). Formuliert nie eine Handlungsanweisung.

**F1 Forensik (nur bei Eskalation)**
- Auslöser. Beneish über Schwelle, Restatement, Prüferwechsel, starke Abweichung Accruals.
- Rolle. Anhang gezielt nach Erklärungen durchsuchen und das Warnsignal bestätigen oder entkräften.
- Modell. `strong`.

Die Prüfagenten J1 bis J4 beschreibt Abschnitt 7.

### 8.4 Nachrichtenformat zwischen Agenten

Agenten tauschen nie freien Text als einziges Ergebnis aus. Jede Ausgabe ist ein JSON-Objekt, das gegen ein Schema validiert wird. Schemas liegen als Pydantic-Modelle in `src/schemas/` und werden zusätzlich als JSON-Schema exportiert.

Gemeinsamer Umschlag für jede Agentenausgabe.

```json
{
  "envelope": {
    "run_id": "2026-10-22T06-00Z",
    "agent_id": "A3_fundamental",
    "agent_version": "1.2.0",
    "prompt_hash": "sha256:...",
    "model_class": "strong",
    "model": "<aufgelöst aus config/models.yaml>",
    "lei": "529900...",
    "input_refs": ["metrics:run/2026-10-22/529900.../*", "doc:sha256:ab12..."],
    "created_at": "2026-10-22T06:14:03Z",
    "status": "draft"
  },
  "claims": [
    {
      "claim_id": "c-0007",
      "text": "Die EBIT-Marge ist seit 2021 jedes Jahr gestiegen.",
      "type": "quantitative",
      "metric_refs": ["ebit_margin@2021..2025"],
      "evidence": [{"doc_hash": "sha256:ab12...", "page": 87, "quote": "..."}],
      "confidence": 0.9
    }
  ],
  "payload": { }
}
```

Der Status durchläuft `draft`, `checked`, `verified`, `rejected`, `escalated`. Nur Claims mit `verified` erreichen den Synthese-Agenten.

### 8.5 Ablauf und Kommunikation

Die Agenten kommunizieren über den Orchestrator und das Dateisystem, nicht direkt miteinander. Das macht jeden Schritt nachvollziehbar und wiederholbar.

```
for kandidat in shortlist (parallel, max 5 gleichzeitig):
    A1 falls Dokumente fehlen
    A2 (2x) falls Werte fehlen        -> J1 vergleicht beide Extraktionen
    P4 Kennzahlen neu berechnen
    A3, A4, A6 parallel
    A5 nach A3 und A4
    J1 rechnet alle zitierten Zahlen blind nach
    J2 prüft jede Behauptung gegen Quelle
    A7 Bear-Fall, dann Erwiderung A3/A5 (max 2 Runden)
    F1 falls Forensik-Flag
    J3 Jury bewertet Gesamtfall
    Status -> verified | escalated | rejected
A8 Portfolio über alle verified-Kandidaten
A9 Bericht
J4 Endkontrolle des Berichts
Dashboard aktualisieren, Benachrichtigung
```

Dateilayout je Lauf.

```
runs/<run_id>/
  manifest.json          Konfigurations-Hashes, Modellversionen, Datenstand
  universe.parquet
  screening.parquet
  candidates/<lei>/
     A3_fundamental.json  A4_qualitative.json  A5_valuation.json
     A6_insider.json      A7_bear.json         rebuttal_1.json
     J1_numbers.json      J2_grounding.json    J3_jury.json
     F1_forensics.json    decision.json
  portfolio.json
  report.md  report.html
  J4_final_check.json
  log.jsonl              jede Werkzeug- und Modellanfrage mit Zeit, Tokens, Kosten
```

### 8.6 Fehlerbehandlung

| Situation | Reaktion |
|---|---|
| Ausgabe verletzt Schema | bis zu 2 Wiederholungen mit Fehlermeldung im Prompt, dann `escalated` |
| Datenquelle nicht erreichbar | 3 Wiederholungen mit wachsender Pause, dann Kandidat überspringen und im Bericht vermerken |
| Zeitlimit je Kandidat (Default 20 Minuten) | Kandidat `escalated` |
| Kostenbudget je Lauf erreicht (`max_cost_per_run_eur`) | Lauf mit bisherigen Ergebnissen abschließen, Rest vermerken |
| Widerspruch zweier Quellen über 5 Prozent | Kandidat `escalated` mit beiden Werten |

---

## 9. Ablauf eines Laufs

### 9.1 Rhythmus

- Hauptlauf alle zwei Wochen, Default Mittwoch 06:00 Uhr Europe/Berlin.
- Täglicher Leichtlauf (nur Python, keine LLM-Kosten) prüft Ereignisse und löst bei Bedarf eine Einzelanalyse aus.

### 9.2 Ereignisauslöser für Einzelanalysen

| Ereignis | Bedingung |
|---|---|
| Neuer Bericht | neuer Jahres- oder Halbjahresbericht bei Bestand, Kaufkandidat oder Beobachtungsliste |
| Insider-Cluster | Cluster nach 3.8 Punkt 5 bei einem Titel im Universum |
| Kursbewegung | Bestandstitel mehr als 20 Prozent unter Kaufkurs oder 52-Wochen-Hoch |
| Warnsignal | neue Ad-hoc-Mitteilung zu Prognosesenkung, Prüferwechsel, Restatement |

### 9.3 Laufschritte

1. Konfiguration laden, Hashes ins Manifest.
2. Bestände aktualisieren (Import, Abschnitt 9.6) und Durchschau rechnen.
3. Universum aktualisieren (monatlich) oder aus Cache.
4. Daten nachladen (inkrementell, nur neue Einreichungen).
5. P2 bis P6 deterministisch für alle Unternehmen.
6. Liste der Tiefenanalysen aus der Kategorie-Anfrage (9.8), allen Bestandstiteln und der Beobachtungsliste bilden.
7. Tiefenanalyse (8.5).
8. Bestandsprüfung (Abschnitt 10), Portfolio, Bericht, Endkontrolle.
9. Dashboard bauen und veröffentlichen, Benachrichtigung.
10. Papierdepot fortschreiben (Abschnitt 14).

### 9.4 Neuanalyse statt Wiederholung

Hat sich bei einem Titel seit dem letzten Lauf weder ein Bericht noch ein Insidergeschäft noch der Kurs um mehr als 10 Prozent verändert, übernimmt das System die vorige Tiefenanalyse und rechnet nur Bewertung und Portfolio-Passung neu. Das spart den Großteil der Kosten.

### 9.5 Hysterese gegen Hin-und-Her

- Ein Unternehmen wird erst Kaufkandidat, wenn es Note A oder B in zwei aufeinanderfolgenden Läufen erreicht oder eine Einzelanalyse es bestätigt.
- Notenbedingte Verkaufsprüfung erst bei Note D oder E in zwei Läufen (HOLD-03) oder bei einem Stopp-Flag.
- Zwischen Note B (Kauf) und Note D (Verkaufsprüfung) liegt bewusst die neutrale Note C als Puffer.

### 9.6 Import der Bestände

- Trade Republic. CSV-Export der Transaktionen aus der App oder über `pytr export_transactions` (optional). Die Zugangsdaten bleiben ausschließlich auf Lucas Rechner, nie in der Cloud.
- Baader-Depot. CSV oder manuell gepflegte `data/holdings_manual.yaml` mit ISIN und Stückzahl.
- Nach jedem Import zeigt das System Abweichungen zum vorigen Stand zur Bestätigung.

---

### 9.7 Den Agenten starten

Grundsatz. Die quantitative Note (Abschnitt 6) wird bei jedem Lauf für alle Unternehmen berechnet. Das kostet keine Modellaufrufe. Die Kategorie, die Luca wählt, bestimmt nur, welche Unternehmen zusätzlich eine Tiefenanalyse mit Agenten bekommen. Bestandstitel werden immer vollständig geprüft (Abschnitt 10).

| Weg | Befehl | Wann |
|---|---|---|
| In Claude Code | im Repository `claude` starten, dann `/stockagent` | Normalfall. Der Skill fragt die Kategorie ab (9.8), zeigt den Laufplan und startet nach Bestätigung |
| Im Terminal ohne Claude Code | `uv run stockagent run` | Dieselben Fragen als Terminal-Dialog (Bibliothek `questionary`) |
| Ohne Rückfragen | `uv run stockagent run --category sector:health_care --region europe --size small,mid --depth standard --budget-eur 10 --yes` | Skripte und Wiederholungen |
| Zeitplan | `uv run stockagent run --profile scheduled --yes` | Liest `config/run_profiles.yaml`, stellt keine Fragen |
| Nur das Depot | `uv run stockagent review-holdings` oder `/depot-check` | Bestandsprüfung allein |
| Einzeltitel | `/analyze-stock <ISIN oder Name>` oder `uv run stockagent analyze <ISIN>` | Gezielte Nachfrage |
| Status und Ergebnisse | `uv run stockagent status`, `uv run stockagent dashboard --open` | Letzte Läufe, offene Eskalationen |

Vor jedem Lauf zeigt das System einen Laufplan mit Datenstand, Anzahl quantitativ bewerteter Unternehmen, Anzahl geplanter Tiefenanalysen, geschätzten Kosten und Dauer. Ohne `--yes` startet der Lauf erst nach Bestätigung.

### 9.8 Kategorie-Abfrage

In Claude Code nutzt der Skill `/stockagent` das Werkzeug AskUserQuestion. Es erlaubt bis zu vier Fragen mit je zwei bis vier Antwortoptionen, Mehrfachauswahl und immer ein Freitextfeld. Der Dialog läuft deshalb in zwei Runden. Im Terminal stellt `questionary` dieselben Fragen.

**Runde 1**

| Frage | Optionen | Mehrfachauswahl |
|---|---|---|
| Was soll ich bewerten? | Branche, Region oder Land, Anlagestil, Gesamtmarkt (beste Noten). Freitext für Thema oder Einzeltitel | nein |
| Welche Größenklassen? | Large und Mega, Mid, Small, Micro und Nano | ja |
| Wie tief? | Schnell (nur Noten, keine Tiefenanalyse), Standard (Tiefenanalyse der besten 10), Tief (beste 25) | nein |
| Mein Depot mitprüfen? | Ja (empfohlen), Nein | nein |

**Runde 2 (abhängig von Runde 1)**

| Auswahl | Rückfrage |
|---|---|
| Branche | Der Skill zeigt die nummerierte Liste der Branchen (Grundlage `config/sectors.yaml` mit 11 Hauptbranchen und Unterbranchen) als Text und nimmt die Auswahl über das Freitextfeld an, etwa "2, 5" |
| Region oder Land | Deutschland, Europa, Nordamerika, Asien-Pazifik und Schwellenländer. Einzelne Länder über Freitext |
| Anlagestil | Qualität, günstige Bewertung, Wachstum, Dividende. Freitext für "Insider-Käufe" oder "Turnaround" |
| Thema (Freitext, etwa "Halbleiter" oder "Wasser") | Der Kategorie-Agent A0 sucht passende Unternehmen ausschließlich in den gespeicherten Geschäftsbeschreibungen und Branchencodes, nie aus Vorwissen (HR-04). Er zeigt die Trefferliste mit Belegstelle je Unternehmen. Luca bestätigt oder streicht, bevor Tiefenanalysen starten |
| Einzeltitel | Auflösung von Name oder Ticker auf ISIN und LEI. Bei mehreren Treffern Auswahlfrage |

Die Antworten werden in `runs/<run_id>/request.json` gespeichert und als Vorschlag für den nächsten Start in `state/last_request.yaml` abgelegt.

Innerhalb der Kategorie sortiert das System nach Note, dann nach Konfidenz. Tiefenanalysen bekommen die besten Unternehmen mit Konfidenz K1 bis K3. Zusätzlich gehen immer alle Bestandstitel und die Beobachtungsliste in die Tiefenanalyse.

Für den Zeitplan definiert `config/run_profiles.yaml` das Profil `scheduled`. Default ist eine Rotation durch die 11 Hauptbranchen (eine Branche je Lauf, nach rund fünf Monaten ist jede Branche einmal tief analysiert), dazu die besten 5 Unternehmen des Gesamtmarkts und das Depot.

### 9.9 Rückfragen während und nach dem Lauf

Der Agent fragt Luca nur an festen Stellen. Beim Start fragt er nach der Kategorie. Bei einem Themen-Lauf bestätigt Luca die Trefferliste. Nach dem Lauf werden eskalierte Fälle vorgelegt (`/review-escalations` in Claude Code oder GitHub-Issues, Abschnitt 16.14). Bei einem neuen Kauf bestätigt Luca die Thesenkarte (Abschnitt 10.2). In Läufen nach Zeitplan stellt er keine Fragen. Was eine Entscheidung braucht, landet in der Eskalations-Warteschlange.

---

## 10. Bestandsprüfung und Verkaufslogik

### 10.1 Grundsatz

Jeder Titel in Lucas Depot wird in jedem Lauf vollständig geprüft, unabhängig von der gewählten Kategorie. Die Verkaufslogik folgt drei Befunden der Verhaltensforschung.

| Befund | Quelle | Folgerung |
|---|---|---|
| Anleger verkaufen Gewinner zu früh und halten Verlierer zu lange (Dispositionseffekt) | Shefrin und Statman (1985, Journal of Finance) | Kaufkurs spielt für das Verkaufsurteil keine Rolle, nur für die Steuer |
| Privatanleger verkaufen eher Gewinner. Die verkauften Gewinner entwickeln sich danach besser als die gehaltenen Verlierer | Odean (1998, Journal of Finance) | Kursgewinn allein ist kein Verkaufsgrund |
| Die aktivsten Privatanleger erzielen nach Kosten die schlechtesten Renditen | Barber und Odean (2000, Journal of Finance) | Hohe Hürde für Verkäufe und Tausch |
| Der Vermögenszuwachs des Marktes stammt von wenigen außergewöhnlichen Gewinnern | Bessembinder (2018) | Gewinner mit intakter These laufen lassen |
| Stop-Loss-Regeln helfen nur, wenn Renditen Trendverhalten zeigen, und kosten sonst Rendite | Kaminski und Lo (2014, Journal of Financial Markets) | Keine prozentualen Stop-Loss-Regeln |

### 10.2 Thesenkarte

Für jede Position gibt es eine Thesenkarte in `state/theses/<isin>.yaml`. Bei einem neuen Kauf entwirft der Synthese-Agent sie, Luca bestätigt sie. Für bestehende Positionen erstellt `/depot-check --onboard` beim ersten Lauf Entwürfe, die Luca bestätigt oder ändert.

```yaml
isin: DE000XXXXXXX
erstellt: 2026-10-22
methodology_version: 3.0
these: "Bis zu drei Sätze. Warum dieses Unternehmen über 5 bis 10 Jahre Wert schafft."
kernkennzahlen:
  - metric: roic
    erwartung: ">= 0.15"
    pruefung: jahresbericht
  - metric: revenue_cagr_3y
    erwartung: ">= 0.05"
    pruefung: jahresbericht
kill_kriterien:
  - "Bruttomarge fällt zwei Jahre in Folge um mehr als 3 Prozentpunkte"
  - "Nettoverschuldung über dem 3-fachen EBITDA"
erwartete_note: "B oder besser"
zielgewicht_gesamtvermoegen: 0.02
naechste_ueberpruefung: 2027-04-30
```

Kill-Kriterien sind maschinenprüfbar formuliert. Textliche Kriterien übersetzt Claude Code beim Anlegen in Regeln über Kennzahl-IDs und zeigt die Übersetzung zur Bestätigung.

### 10.3 Prüfungen je Lauf

Die Prüfungen sind deterministisch (`core/holdings_review.py`). Der Bestandsprüfer A10 erklärt die Ergebnisse, prüft qualitative Thesenpunkte gegen neue Berichte und kann wie alle Agenten nur abwerten oder eskalieren (HR-13).

| ID | Prüfung | Auslöser | Ergebnis |
|---|---|---|---|
| HOLD-01 | These intakt | Eine Kernkennzahl liegt in zwei aufeinanderfolgenden Berichtsperioden außerhalb ihrer Erwartung | Halten und beobachten, bei zwei Kernkennzahlen Verkauf prüfen |
| HOLD-02 | Kill-Kriterium | ein Kriterium erfüllt | Verkauf prüfen |
| HOLD-03 | Note | D oder E in zwei aufeinanderfolgenden Läufen | Verkauf prüfen |
| HOLD-04 | Stopp-Flag | Going Concern, Zinsdeckung unter 2, Restatement mit Hinweis auf Bilanzmanipulation | Verkauf prüfen, sofortige Eskalation |
| HOLD-05 | Bewertung extrem | Bewertungssäule unter dem 10. Perzentil und implizites Wachstum über dem 90. Perzentil der eigenen 10-Jahres-Historie | Teilverkauf prüfen, nur wenn die Position über ihrem Zielgewicht liegt |
| HOLD-06 | Konzentration | Gewicht einschließlich Durchschau über dem 1,5-fachen der Obergrenze aus 6.4 | Teilverkauf auf Zielgewicht prüfen |
| HOLD-07 | Insider | opportunistisches Verkaufscluster nach 3.8 | Halten und beobachten |
| HOLD-08 | Bessere Alternative | Unternehmen derselben Scorecard mit mindestens 15 Punkten höherem Gesamtwert, gleicher oder besserer Konfidenz, als Kaufkandidat verifiziert | Tausch prüfen, mit Steuer- und Kostenrechnung |
| HOLD-09 | Ereignis | Übernahmeangebot, Abspaltung, Delisting | Information und Eskalation |
| HOLD-10 | Datenlage | Konfidenz fällt auf K4 | Halten und beobachten mit Hinweis |

### 10.4 Steuer- und Kostenrechnung

Bei jedem Ergebnis außer "Halten" rechnet das System. Realisierter Gewinn oder Verlust je Steuerlos (FIFO, wie in Deutschland vorgeschrieben), Abgeltungsteuer von 25 Prozent plus Solidaritätszuschlag von 5,5 Prozent darauf, optional Kirchensteuer (`church_tax_rate` in `config/tax.yaml`), verbleibender Sparerpauschbetrag (Default 1.000 EUR, jährlich zu prüfen), Verrechnung im Aktienverlusttopf und Orderkosten. Beim Tausch rechnet es zusätzlich die Mehrrendite, die der Ersatz pro Jahr bringen müsste, um die Steuerzahlung über 5 Jahre auszugleichen. Jede Steuerangabe trägt den Hinweis, dass das System keine Steuerberatung leistet und die Regeln vor einer Entscheidung aktuell zu prüfen sind.

### 10.5 Ergebnisstufen

| Stufe | Bedeutung |
|---|---|
| Halten | These intakt, keine Auffälligkeit |
| Halten und beobachten | einzelne Abweichung, benannte Frühindikatoren |
| Teilverkauf prüfen | Gewicht zu hoch oder Bewertung extrem, These intakt |
| Verkauf prüfen | These verletzt, Kill-Kriterium oder Stopp-Flag |
| Tausch prüfen | deutlich bessere Alternative nach Steuern und Kosten |

Jedes Ergebnis enthält Begründung mit Belegen, die Steuerrechnung und die Frage "Was müsste passieren, damit sich die Einschätzung umkehrt?". Das System formuliert nie "verkaufen", sondern "prüfen". Die Entscheidung trifft Luca.

### 10.6 Ausdrücklich keine Verkaufsgründe

- Kursverlust seit dem Kauf allein
- Kursgewinn seit dem Kauf allein
- prozentuale Stop-Loss-Marken
- Nachrichten ohne erkennbare Wirkung auf Kennzahlen oder These
- ein schwacher Einzelquartalswert ohne Bestätigung im Folgequartal

---

## 11. Verifikationssystem (LLM-as-a-Judge)

### 11.1 Was die Forschung sagt

| Befund | Quelle | Folgerung |
|---|---|---|
| LLM-Richter haben systematische Verzerrungen. Bevorzugung der ersten Antwort (Positionsbias), längerer Antworten (Längenbias) und eigener Texte (Selbstbevorzugung) | Zheng et al., "Judging LLM-as-a-Judge", NeurIPS 2023 (UC Berkeley, LMSYS). Ye et al., "Justice or Prejudice?", ICLR 2025, katalogisiert 12 Biasarten. Wataoka et al. 2024 zur Selbstbevorzugung | Reihenfolgen vertauschen, Länge normieren, Erzeuger und Richter aus verschiedenen Modellfamilien |
| Positionsbias ist häufig die Ursache hinter Längen- und Selbstbevorzugung | Shi et al., "Judging the Judges", 2024 | Paarvergleiche immer in beiden Reihenfolgen |
| Eine Jury aus mehreren kleineren Modellen verschiedener Familien stimmt besser mit Menschen überein als ein einzelner großer Richter und ist über siebenmal günstiger | Verga et al., "Replacing Judges with Juries", Cohere 2024 | Jury mit 3 Richtern statt Einzelrichter |
| Prüfer, die die Antwort des Erzeugers sehen, übernehmen deren Fehler. Informationsasymmetrie hilft | Li et al., MARCH, ACL 2026 (Alibaba Qwen) | Blinde Nachrechnung vor dem Abgleich |
| Ein Richter mit Werkzeugen, der Zwischenschritte prüft, stimmt in 90 statt 70 Prozent der Fälle mit dem menschlichen Konsens überein | Zhuge et al., "Agent-as-a-Judge", ICML 2025 (KAUST, Meta) | Prüfer bekommen Lesezugriff auf Rohdaten und Rechenskripte |
| Überblick über Methoden und Grenzen | Gu et al. 2024, "A Survey on LLM-as-a-Judge". Li et al. 2024, "LLMs-as-Judges" | Rubriken statt freier Urteile, Kalibrierung gegen Goldstandard |
| Retrieval-Fehler dominieren bei Finanzdokumenten | Islam et al., FinanceBench 2023 | Lange Kontexte, Seitenbezug, keine Vektorsuche als einzige Quelle |

Die Forschung zur Richterzuverlässigkeit stammt aus den USA (Berkeley, Cohere), Europa und dem Nahen Osten (KAUST mit Schmidhuber, Schweiz) und China (Alibaba). Die Ergebnisse widersprechen sich in den Kernpunkten nicht.

### 11.2 Vier Prüfebenen

**Ebene 0, deterministische Prüfungen (Python).** Schemaprüfung, Datenqualität aus 3.2, Wertebereiche (Marge zwischen minus 100 und 100 Prozent), Einheitenkonsistenz. Diese Ebene ist die billigste und fängt den größten Teil der Fehler.

**Ebene 1, J1 Zahlenprüfer (blind).**
- Ablauf. J1 bekommt die Liste aller quantitativen Claims, aber ohne die vom Agenten genannten Werte. Er bestimmt jeden Wert selbst aus `facts` und Skripten. Erst danach vergleicht der Orchestrator.
- Toleranz. Relative Abweichung bis 0,5 Prozent gilt als Übereinstimmung, bis 2 Prozent als Rundung (Warnung), darüber als Fehler.
- Ergebnis je Claim. `match`, `rounding`, `mismatch`, `not_computable`.
- Ein einziger `mismatch` bei einer Kernkennzahl setzt den Kandidaten auf `escalated`.

**Ebene 2, J2 Belegprüfer (Groundedness).**
- Ablauf. Jede qualitative Behauptung wird gegen die zitierte Stelle geprüft. J2 liest die Seite selbst und beantwortet je Claim "Wird die Aussage von der Stelle gedeckt?" mit `supported`, `partially`, `not_supported`, `contradicted`.
- Behauptungen ohne Beleg werden gestrichen, nicht nachträglich belegt.
- Unterschiedliche Modellfamilie als A3 und A4.

**Ebene 3, J3 Jury.**
- Drei Richter, möglichst aus drei Modellfamilien (zum Beispiel Claude, ein Modell von OpenAI oder Google über deren API, ein offenes Modell wie Qwen oder Llama über einen Anbieter). Ist nur Claude verfügbar, werden drei Claude-Richter mit unterschiedlichen Modellgrößen und Rubrik-Perspektiven eingesetzt und der Bericht weist darauf hin, dass die Diversität eingeschränkt ist.
- Jeder Richter bewertet unabhängig nach derselben Rubrik (11.3), mit vertauschter Reihenfolge von Bull- und Bear-Fall in der Hälfte der Aufrufe.
- Aggregation. Median je Kriterium. Übereinstimmung gemessen als Spannweite. Liegt bei einem Kriterium die Spannweite über 2 Punkten (Skala 1 bis 5), gilt die Jury als uneinig.
- Entscheidungsregel. `verified`, wenn kein Kriterium unter 3 liegt, der Median "Gesamtbegründung" mindestens 4 ist und die Jury einig ist. Sonst `escalated`.

**Ebene 4, J4 Endkontrolle.** Prüft den fertigen Bericht. Stimmen alle Zahlen im Text mit `decision.json` überein? Hat jeder Absatz Belege? Enthält der Bericht Formulierungen, die nach Kaufaufforderung oder Garantie klingen? Ist der Bear-Fall vollständig wiedergegeben?

### 11.3 Rubrik für J3 (Skala 1 bis 5 je Kriterium)

| Kriterium | 1 | 3 | 5 |
|---|---|---|---|
| Faktentreue | mehrere ungeprüfte oder falsche Fakten | einzelne kleinere Ungenauigkeiten | alle Fakten belegt und geprüft |
| Vollständigkeit | wichtige Bereiche fehlen (Verschuldung, Bewertung, Risiken) | alle Bereiche, einzelne oberflächlich | alle Bereiche aus 3.3 bis 3.9 substanziell behandelt |
| Logische Konsistenz | Schlussfolgerung widerspricht Daten | kleinere Sprünge | jede Schlussfolgerung folgt aus Belegen |
| Umgang mit Gegenargumenten | Bear-Fall ignoriert | erwähnt, nicht beantwortet | jedes Hauptrisiko beantwortet oder als offen markiert |
| Bewertungsdisziplin | Annahmen unbegründet oder extrem | plausibel, teils unbegründet | jede Annahme belegt, Sensitivität verstanden |
| Gesamtbegründung | Empfehlung nicht nachvollziehbar | nachvollziehbar mit Lücken | ein kritischer Analyst würde die Herleitung akzeptieren |

Richter müssen je Kriterium zuerst eine Begründung mit Verweisen auf Claim-IDs schreiben und erst danach die Zahl. Ausgabe als JSON gegen Schema.

### 11.4 Maßnahmen gegen bekannte Verzerrungen

| Bias | Maßnahme |
|---|---|
| Positionsbias | Reihenfolge randomisiert und in der Hälfte der Aufrufe vertauscht, Abweichung beider Läufe gemessen |
| Längenbias | Rubrik bewertet ausdrücklich Belegdichte, nicht Umfang. Fallbeschreibungen auf feste Längen gekürzt |
| Selbstbevorzugung | Erzeuger und Prüfer aus verschiedenen Modellen oder mindestens verschiedenen Prompts und Rollen. Herkunft der Texte für Richter verborgen |
| Bestätigungsfehler | Blinde Nachrechnung (J1), Bear-Agent als Pflichtschritt |
| Ablenkung durch bekannte Namen | Für die Jury wird der Firmenname optional anonymisiert (`anonymize_for_jury`, Default an). Glasserman und Lin zeigen, dass Wissen über die Firma das Urteil verzerren kann |
| Nachgiebigkeit unter Druck | Richter sehen keine Erwiderungen auf ihr eigenes Urteil |

### 11.5 Eskalation an Luca

Eskaliert wird bei `mismatch` in Kernkennzahlen, `contradicted` bei einer Behauptung, uneiniger Jury, Forensik-Flag ohne Entkräftung, Datenwiderspruch über 5 Prozent und Stopp-Flags bei Bestandstiteln. Eskalierte Fälle erscheinen im Dashboard in einer eigenen Warteschlange mit den konkreten Streitpunkten. Lucas Entscheidung (`human_decision`, `human_note`) wird gespeichert und fließt in den Goldstandard.

### 11.6 Kalibrierung der Prüfer

1. Goldstandard-Datensatz in `eval/gold/`. Phase 1 mit 20 Unternehmen, für die Luca Kernkennzahlen aus den Originalberichten händisch prüft. Dazu absichtlich fehlerhafte Analysen (falsche Zahl, falsche Periode, erfundene Aussage, fehlender Risikofaktor), um die Fangquote zu messen.
2. Metriken. Fangquote je Fehlerart, Fehlalarmquote, Übereinstimmung Jury mit Luca (Cohens Kappa), Stabilität bei Wiederholung.
3. Mindestanforderung vor Produktivbetrieb. J1 findet mindestens 95 Prozent der eingebauten Zahlenfehler, J2 mindestens 85 Prozent der erfundenen Aussagen.
4. Jede Prompt- oder Modelländerung läuft gegen den Goldstandard. Verschlechterungen blockieren die Änderung (Test in der CI).

---

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
| 1 | Kopf | Name, ISIN, LEI, Scorecard, Rechnungslegungsstandard, Berichts- und Kurswährung, Datenstand, Lauf-ID, Methodik-Version, Register-Hash | Python |
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

---

## 13. Nachvollziehbarkeit und Darstellung

### 13.1 Audit-Trail

- Jede Zahl im Bericht ist anklickbar und führt zu Kennzahl-ID, Formel, Eingabewerten und deren Quelle (XBRL-Konzept oder PDF-Seite mit Zitat).
- Jeder Lauf ist reproduzierbar. Das Manifest enthält Git-Commit, Hashes aller Konfigurationsdateien, Modellnamen und -versionen, Prompt-Hashes und den Datenstand (höchstes `published_at`).
- Rohdokumente werden nie gelöscht oder überschrieben.
- `log.jsonl` protokolliert jede Modellanfrage und jeden Werkzeugaufruf mit Tokens und Kosten.

### 13.2 Entscheidungsvorlage (Bericht je Lauf)

Aufbau der Laufübersicht `report.md` und `report.html`. Jede verlinkte Einzelanalyse folgt der Gliederung aus 12.3.

1. Kopf. Datum, Lauf-ID, Datenstand, Methodik-Version, Hinweis "Recherche-Grundlage, keine Anlageberatung".
2. Kurzfassung in fünf Sätzen. Was hat sich seit dem letzten Lauf geändert?
3. Kaufkandidaten (Tabelle). Name, ISIN, Branche, Land, Note · Konfidenz · Risiko, Kategorie, Sicherheitsmarge, implizites Wachstum, Insider-Signal, Vorschlag in EUR und Prozent, Überzeugungsstufe.
4. Je Kaufkandidat eine Seite. These in drei Sätzen, Kennzahlen-Übersicht mit Trend, Bewertungsdiagramm (Football Field), Bear-Fall mit Beobachtungsindikatoren, Prüfstatus aller Ebenen, Belegliste.
5. Bestandsprüfung mit Ergebnisstufe aus 10.5, Begründung und Steuerrechnung je Position.
6. Beobachtungsliste mit dem Grund, warum (noch) nicht.
7. Eskalierte Fälle mit Streitpunkten.
8. Portfolio-Wirkung. Allokation vorher und nachher, Länder, Branchen, Währungen, Top-10-Risiken einschließlich Durchschau.
9. Papierdepot-Stand gegen Vergleichsindex.
10. Methodische Hinweise und Änderungen seit dem letzten Lauf.

### 13.3 Dashboard

Das Dashboard ist eine statische Webseite, die aus den Laufdaten gebaut wird. Damit läuft es überall und braucht keinen Server.

- Technik. Ein Python-Skript `build_dashboard.py` schreibt eine einzelne HTML-Datei mit eingebetteten Daten (JSON) und Diagrammen in Plotly.js oder ECharts. Alternative für lokale Nutzung mit Interaktion ist Streamlit. Die statische Variante ist Default, weil sie als Artifact in Claude veröffentlicht oder einfach als Datei geöffnet werden kann.
- Veröffentlichung. Optional als privates Artifact in Claude, das bei jedem Lauf aktualisiert wird.

Ansichten.

| Ansicht | Inhalt |
|---|---|
| Übersicht | Kacheln mit Anzahl Kaufkandidaten, Eskalationen, Papierdepot gegen Index, Einzeltitelanteil gegen Ziel. Darunter die Kandidatentabelle, sortier- und filterbar |
| Chancen-Karte | Streudiagramm Qualitätsscore (x) gegen Bewertungsscore (y), Punktgröße Marktkapitalisierung, Farbe Kategorie. Oben rechts liegen gute Firmen zu fairen Preisen |
| Kandidatenseite | Score-Zerlegung als Wasserfall, Kennzahlen-Zeitreihen mit Branchenmedian als Band, Football Field, Reverse-DCF mit implizitem Wachstum gegen Historie, Insider-Zeitachse über dem Kurs, Bear-Fall, Prüfprotokoll mit Ampel je Ebene, Belegliste mit Links |
| Portfolio | Gestapelte Balken Ist, Ziel und Vorschlag, Länder- und Branchenvergleich, Top-10-Risiken einschließlich Durchschau |
| Eskalationen | Warteschlange mit Streitpunkten und Eingabefeld für Lucas Entscheidung (im lokalen Modus schreibt das Feld in `decisions`) |
| Historie | Alle Läufe, Score-Verlauf je Titel, Papierdepot-Kurve gegen Index |
| Methodik | aktuelle Gewichte, Schwellen und Versionen, Änderungsprotokoll |

Gestaltung. Farben ausschließlich für Kategorien und Ampeln, nie als einziger Bedeutungsträger (zusätzlich Text oder Symbol). Hell- und Dunkelmodus. Jede Zahl mit Tooltip zur Quelle.

### 13.4 Benachrichtigung

Nach jedem Lauf eine kurze Nachricht mit Anzahl Kaufkandidaten, Eskalationen und Link zum Dashboard. Kanal konfigurierbar (E-Mail per SMTP, Telegram-Bot, Push über Claude).

---

## 14. Backtesting, Papierdepot und Erfolgsmessung

### 14.1 Was rückwärts testbar ist

Nur der deterministische Teil (Klassifikation, Kennzahlen, Scores, Noten) wird historisch getestet, mit Point-in-Time-Daten ab 2010 für US-Werte und ab 2020 für ESEF-Werte. LLM-Urteile werden nicht rückwärts getestet, weil die Modelle die Kursentwicklung aus dem Training kennen. Die Literatur dazu (Glasserman und Lin 2023, Sarkar und Vafa 2024, He et al. zu ChronoGPT 2025) zeigt, dass das Ausmaß der Verzerrung von Modell und Anwendung abhängt und nie sicher null ist.

Regeln für den Backtest. Kosten von 1 EUR je Order und ein Spread-Abschlag, Rebalancing zweiwöchentlich, keine Überlebensverzerrung (delistete Titel bleiben mit Endwert drin), keine Optimierung der Gewichte auf dem Testzeitraum. Wer Gewichte verändert, testet auf einem getrennten Zeitraum.

### 14.2 Papierdepot

Ab dem ersten Lauf führt das System ein Papierdepot, das jede Empfehlung zum Schlusskurs des Folgetags umsetzt. Daneben ein Vergleichsdepot mit gleichem Betrag in einem MSCI-World-ETF.

### 14.3 Erfolgsmaße

- Rendite und Volatilität gegenüber dem Vergleichsdepot.
- Trefferquote je Kategorie. Wie haben sich Kaufkandidaten, Beobachtungen und Ausgeschlossene nach 6, 12 und 24 Monaten entwickelt?
- Prüferqualität aus 7.6.
- Kosten je Lauf.

### 14.4 Abbruchkriterium (vorab festgelegt)

Liegt das Papierdepot nach 24 Monaten mehr als 5 Prozentpunkte hinter dem Vergleichsdepot und zeigt die Trefferquote keinen Vorsprung der Kaufkandidaten vor den Ausgeschlossenen, wird der Einzeltitelanteil zugunsten von ETFs reduziert. Dieses Kriterium steht in `config/portfolio.yaml` und wird nicht nachträglich verschoben. Grund ist Bessembinders Befund (Abschnitt 1, Nr. 12). Ohne vorab festgelegtes Kriterium neigt man dazu, schwache Ergebnisse wegzuerklären.

---

## 15. Technische Grundsatzentscheidung

### 15.1 Claude Code oder Claude Agent SDK

Beides, mit klarer Arbeitsteilung.

| Aufgabe | Werkzeug | Grund |
|---|---|---|
| System bauen, testen, erweitern | Claude Code interaktiv | Schnellste Entwicklung, Subagents für parallele Recherche, Hooks für Qualitätsregeln |
| Produktiver Lauf alle zwei Wochen | Python-Orchestrator mit Claude Agent SDK (`claude-agent-sdk`) | Ablauf ist deterministisch steuerbar, Budgets und Zeitlimits je Agent, Schemaprüfung jeder Ausgabe, Wiederholungen ohne Sprachmodell-Entscheidung. Das SDK nutzt dieselben Subagent-Definitionen und Werkzeuge wie Claude Code |
| Ad-hoc-Analyse eines Einzeltitels | Claude Code mit Slash-Befehl `/analyze <ISIN>` (Skill) | Luca kann jederzeit nachfragen und nachbohren |

Ein vollständig vom Sprachmodell gesteuerter Ablauf ("Claude, mach den Lauf") ist für den produktiven Betrieb ungeeignet, weil Reihenfolge, Prüfpflichten und Informationsasymmetrie nicht verlässlich eingehalten würden. Der Orchestrator ist deshalb normaler Python-Code, der Agenten als Funktionen aufruft.

### 15.2 Ausführungsort und Zeitplan

| Option | Vorteile | Nachteile | Empfehlung |
|---|---|---|---|
| Geplante Aufgabe in der Claude-Desktop-App (lokal) | Zugriff auf lokale Dateien, Depot-Exporte bleiben auf dem Rechner | Rechner muss laufen | Für den Start |
| Routine in Claude Code (Cloud, Mindestintervall 1 Stunde) | Läuft ohne eigenen Rechner, Ergebnis als Sitzung einsehbar | Standard-Netzwerkzugang erlaubt nur eine Positivliste. Für `data.sec.gov`, `filings.xbrl.org`, `bafin.de` und Datenanbieter muss die Umgebung auf "Custom" mit eigenen Domains gestellt werden. Bestände müssen im Repository liegen (privat halten) | Sobald alles stabil läuft |
| GitHub Actions mit Zeitplan | Kostenlos für private Repos im Rahmen, volle Kontrolle über Netzwerk | API-Schlüssel als Secrets, Bestände als verschlüsseltes Secret | Alternative zur Routine |

Unabhängig vom Ort startet der Zeitplan immer denselben Befehl `uv run stockagent run --profile scheduled --yes`.

### 15.3 Technologieauswahl

| Bereich | Wahl |
|---|---|
| Sprache | Python 3.12 |
| Paket- und Umgebungsverwaltung | `uv` |
| Datenmodelle und Schemas | Pydantic v2 |
| Datenbank | DuckDB, Spaltendateien als Parquet |
| Datenrahmen | Polars (schnell) mit pandas nur wo Bibliotheken es verlangen |
| SEC-Daten | `edgartools` |
| ESEF-Daten | `xbrl-filings-api`, für Detailauswertung Arelle |
| PDF | Docling, optional LlamaParse |
| Statistik | NumPy, SciPy (Theil-Sen über `scipy.stats.theilslopes`) |
| CLI | Typer |
| Konfiguration | YAML plus Pydantic-Settings, Geheimnisse in `.env` (nie committen) |
| Diagramme | Plotly (Python erzeugt JSON, HTML bindet Plotly.js ein) |
| Tests | pytest, Hypothesis für Formeln, Snapshot-Tests für Berichte |
| Qualität | ruff, mypy im Strict-Modus für `src/stockagent/core` |
| Agenten | `claude-agent-sdk`, Subagent-Definitionen als Markdown in `.claude/agents/` |

---

## 16. Umsetzung mit Claude Code im Detail

### 16.1 Repository-Struktur

```
stockagent/
├── CLAUDE.md
├── docs/
│   ├── SPEC.md                    dieses Dokument
│   ├── METHODOLOGY_CHANGELOG.md
│   └── adr/                       Architekturentscheidungen
├── .claude/
│   ├── settings.json              Berechtigungen, Hooks
│   ├── agents/                    erzeugt aus agents_src/, nicht von Hand bearbeiten
│   └── skills/
│       ├── stockagent/SKILL.md
│       ├── depot-check/SKILL.md
│       ├── analyze-stock/SKILL.md
│       ├── add-metric/SKILL.md
│       └── review-escalations/SKILL.md
├── .github/
│   ├── workflows/ (ci.yml, eval.yml, scheduled-run.yml, daily-light.yml)
│   └── pull_request_template.md
├── agents_src/                    Vorlagen A0..A10, J1..J4, F1 mit Modellklasse
├── scripts/ (render_agents.py, hooks/)
├── config/
│   ├── metrics.yaml  scoring.yaml  scorecards.yaml  sectors.yaml  portfolio.yaml
│   ├── accounting_adjustments.yaml  hyperinflation.yaml  withholding_tax.yaml  tax.yaml
│   ├── models.yaml  concept_map.yaml  insider_thresholds.yaml  run_profiles.yaml
│   └── sources.yaml
├── state/                         Thesenkarten, letzte Anfrage, Bestände (Bestände nie im Klartext committen)
├── src/stockagent/
│   ├── cli.py
│   ├── core/                      reine Funktionen ohne I/O
│   │   ├── registry.py  scores.py  grading.py  valuation.py  accounting.py  fx.py
│   │   ├── insider.py  portfolio.py  holdings_review.py  decisions.py  pit.py
│   ├── gates/ (schema, number, evidence, quote, wording, consistency)
│   ├── data/
│   │   ├── sources/ (sec.py, esef.py, vendor.py, bafin.py, etf_holdings.py, fx.py, rates.py)
│   │   ├── store.py               DuckDB-Zugriff
│   │   └── quality.py             Prüfungen aus 3.2
│   ├── agents/
│   │   ├── runner.py              Aufruf über Agent SDK, Schema-Validierung, Retries
│   │   ├── prompts/               versionierte Prompt-Vorlagen
│   │   └── tools/                 Skripte, die Agenten aufrufen dürfen
│   ├── judges/ (numbers.py, grounding.py, jury.py, final_check.py)
│   ├── schemas/                   Pydantic-Modelle
│   ├── orchestrator.py
│   ├── report/ (render.py, templates/)
│   └── dashboard/ (build.py, template.html)
├── eval/
│   ├── gold/                      Goldstandard
│   └── run_eval.py
├── tests/
├── data/                          in .gitignore, außer Beispielen
└── runs/                          in .gitignore
```

### 16.2 Schichtenregel

`core/` enthält nur reine Funktionen, die DataFrames oder Pydantic-Objekte annehmen und zurückgeben. Kein Netzwerk, keine Datenbank, kein Sprachmodell. Damit ist jede Formel isoliert testbar und auch ohne Agenten nutzbar.

### 16.3 Vorlage für CLAUDE.md

```markdown
# stockagent

Recherche-System für Einzelaktien. Vollständige Spezifikation in docs/SPEC.md. Bei Widersprüchen gilt SPEC.md.

## Unverhandelbare Regeln
Die harten Regeln HR-01 bis HR-16 stehen in docs/SPEC.md Abschnitt 0.1. Lies sie zu Beginn jeder Sitzung.
- Sprachmodelle liefern nie Zahlen. Formeln nur in src/stockagent/core/registry.py.
- Jeder Wert braucht Quelle (doc_hash+page oder XBRL-Konzept+Periode), Währung, Einheit, Standard, Periode.
- Point-in-Time über store.pit_query(as_of=...).
- Keine Order-Funktionen, kein Schreibzugriff auf Broker.
- Schwellen, Gewichte und Modellzuordnung nur in config/.
- Prüfagenten sehen geprüfte Werte erst nach eigenem Ergebnis.
- Nie direkt auf main pushen. Branch je Phase, Pull Request, CI grün.
- Wenn etwas unklar ist, frag nach statt zu raten.

## Befehle
- uv run pytest            Tests
- uv run ruff check . && uv run mypy src
- uv run stockagent run [--profile scheduled --yes]
- uv run stockagent review-holdings
- uv run stockagent analyze <ISIN>
- uv run python scripts/render_agents.py   Agent-Dateien aus agents_src/ erzeugen
- uv run python eval/run_eval.py   Goldstandard

## Konventionen
- Neue Kennzahl: Eintrag in config/metrics.yaml, Funktion in core/registry.py, Test mit Handrechnung aus echtem Bericht.
- Jede Methodikänderung: Eintrag in docs/METHODOLOGY_CHANGELOG.md, methodology_version erhöhen.
- Prompts versioniert in src/stockagent/agents/prompts/, Änderung erfordert eval-Lauf.
```

### 16.4 Subagent-Definitionen

Claude Code liest Subagents aus `.claude/agents/*.md`. Diese Dateien erzeugt `scripts/render_agents.py` aus den Vorlagen in `agents_src/`. Dabei ersetzt das Skript den Platzhalter `{{ model.<klasse> }}` durch den Eintrag aus `config/models.yaml` und prüft, dass die Pflicht-Präambel aus 17.6 vorhanden ist. Pflichtfelder sind `name` und `description`. Weitere nutzbare Felder sind `tools`, `disallowedTools`, `model`, `permissionMode`, `maxTurns`, `skills`, `mcpServers`, `hooks`, `memory`, `effort`, `background` und `isolation`. Subagents starten mit leerem Kontext und bekommen nur ihren Systemprompt, die Aufgabe und die CLAUDE.md-Dateien. Genau das erzeugt die gewünschte Informationsasymmetrie. Standardmäßig laufen höchstens 20 Subagents gleichzeitig, verschachtelt bis drei Ebenen tief.

Beispiel Zahlenprüfer (Vorlage in `agents_src/`).

```markdown
---
name: j1-number-checker
description: Prüft quantitative Claims blind durch eigene Berechnung aus der Datenbank. Nur vom Orchestrator aufrufen.
tools: Read, Bash
disallowedTools: Write, Edit, WebSearch, WebFetch
model: {{ model.standard }}
maxTurns: 40
omitClaudeMd: true
---
{{ preamble }}

Du bist Prüfer für Finanzkennzahlen. Du erhältst eine Liste von Claims mit claim_id,
Kennzahl-ID, Unternehmen und Periode. Die vom Analysten genannten Werte erhältst du NICHT.

Für jeden Claim:
1. Ermittle den Wert ausschließlich über die Werkzeuge query_facts und compute_metric.
2. Rechne niemals im Kopf. Jede Zahl stammt aus einer Werkzeugausgabe.
3. Ist der Wert nicht berechenbar, gib not_computable mit Grund an.

Antworte nur mit JSON nach Schema schemas/j1_output.json.
```

Beispiel Bear-Agent.

```markdown
---
name: a7-bear-case
description: Formuliert die stärkste belegte Gegenposition zu einem Kaufkandidaten inklusive Pre-Mortem.
tools: Read, Grep, Bash
disallowedTools: Write, Edit
model: {{ model.strong }}
maxTurns: 30
---
{{ preamble }}

Du bist ein skeptischer Analyst. Deine Aufgabe ist nicht, die Aktie schlechtzureden,
sondern die drei realistischsten Wege zu finden, wie ein Investment über 5 bis 10 Jahre scheitert.
Jede Aussage braucht eine Kennzahl-ID oder eine Belegstelle (doc_hash, Seite, Zitat).
Pre-Mortem: Es ist 2031, die Aktie hat 50 Prozent verloren. Was ist passiert?
Für jedes Risiko nenne einen beobachtbaren Frühindikator.
Antworte nur mit JSON nach Schema schemas/a7_output.json.
```

Im SDK-Orchestrator werden dieselben Definitionen geladen. Die Bash-Befehle der Prüfer werden nicht über das `tools`-Feld eingeschränkt, sondern über einen `PreToolUse`-Hook im Frontmatter, der nur Aufrufe von `stockagent.agents.tools.*` durchlässt. Strukturierte Ausgabe erzwingt der Runner über JSON-Schema und validiert anschließend mit Pydantic.

### 16.5 Hooks

Hooks sind Shell-Befehle, die Claude Code bei Ereignissen ausführt. Exit-Code 2 blockiert die Aktion und gibt die Fehlermeldung an Claude zurück. Konfiguration in `.claude/settings.json`.

| Ereignis | Hook | Zweck |
|---|---|---|
| `PreToolUse` auf `Bash` | `scripts/hooks/block_broker.sh` | blockiert alles mit `order`, `pytr ... buy/sell`, `limit_order`, `market_order` |
| `PreToolUse` auf `Edit|Write` | `scripts/hooks/protect_raw.sh` | verhindert Änderungen in `data/raw/` und an Goldstandard-Dateien |
| `PostToolUse` auf `Edit|Write` in `src/` | `uv run ruff check --fix` und betroffene Tests | sofortige Rückmeldung |
| `PostToolUse` auf `Edit|Write` in `config/` oder `prompts/` | Erinnerung, Changelog und Eval-Lauf nachzuziehen | Methodik-Disziplin |
| `SubagentStop` | `scripts/hooks/validate_agent_output.py` | prüft, ob die Subagent-Ausgabe gegen ihr Schema validiert |
| `Stop` | `uv run pytest -q -x` | Claude beendet keine Arbeitssitzung mit roten Tests |

### 16.6 Skills

| Skill | Auslöser | Inhalt |
|---|---|---|
| `stockagent` | `/stockagent` | Kategorie-Abfrage nach 9.8 mit AskUserQuestion, Laufplan zeigen, nach Bestätigung `uv run stockagent run` mit den Antworten starten, Fortschritt melden, Ergebnis zusammenfassen, Dashboard öffnen |
| `depot-check` | `/depot-check [--onboard]` | Bestandsprüfung nach Abschnitt 10. Mit `--onboard` Entwürfe der Thesenkarten für Altbestände zur Bestätigung |
| `analyze-stock` | `/analyze-stock <ISIN oder Name>` | Einzelanalyse über den Orchestrator, danach Analyse mit 14 Abschnitten öffnen |
| `add-metric` | "füge Kennzahl X hinzu" | Schritt-für-Schritt nach Abschnitt 18.1 |
| `review-escalations` | `/review-escalations` | eskalierte Fälle einzeln mit Luca durchgehen und Entscheidungen speichern |

### 16.7 MCP-Server

Für v1 nicht nötig, weil alle Datenquellen über Python-Skripte angebunden sind. Sinnvoll später.

- Ein eigener MCP-Server `stockagent-data` mit Werkzeugen `query_facts`, `compute_metric`, `get_document_page`, `search_filings`. Vorteil ist, dass Claude in jeder Sitzung und auf jeder Oberfläche dieselben geprüften Werkzeuge nutzt. Bauen mit dem Python-MCP-SDK, sobald die Skripte stabil sind.
- Kommerzielle Finanzdaten-MCP-Server nur, wenn sie Quellenangaben je Wert liefern.

### 16.8 Berechtigungen

`.claude/settings.json` erlaubt ohne Rückfrage Lesen im Repository, `uv run` für Tests und das CLI sowie Webzugriff auf die Domains aus `config/sources.yaml`. Rückfrage bei allem anderen. Verboten sind Zugriffe auf `~/.pytr/`, `.env` und jede Order-Funktion.

### 16.9 Kosten und Geheimnisse

- API-Schlüssel (Anthropic, Datenanbieter, optional weitere Modellanbieter für die Jury) in `.env`, in der Cloud als Secret.
- Kostenschätzung je Hauptlauf mit bis zu 25 Tiefenanalysen plus Depot und Wiederverwendung nach 9.4 im niedrigen zweistelligen Euro-Bereich. Das System misst die tatsächlichen Kosten in `log.jsonl` und bricht bei `max_cost_per_run_eur` (Default 25) ab.
- Prompt-Caching nutzen, indem Systemprompts und Methodik-Texte am Anfang jeder Anfrage stehen und sich zwischen Kandidaten nicht ändern.

### 16.10 Bauphasen mit Abnahmekriterien

Jede Phase entsteht auf einem eigenen Branch `phase-NN-kurzname` und endet mit einem Pull Request, dessen CI grün ist. Luca führt den Merge durch.

| Phase | Inhalt | Abnahme |
|---|---|---|
| 0 Gerüst | GitHub-Repository (16.11), uv, CI, CLAUDE.md, Hooks, Schemas, Gates aus 12.6 als leere Prüfungen mit Tests, CLI-Gerüst | CI grün, Hook blockiert einen Test-Order-Befehl, Zahlen-Gate lehnt Testtext mit Ziffern ab |
| 1 Daten USA | SEC-Anbindung, DuckDB, Point-in-Time, Datenqualität 3.2 | 10 US-Firmen geladen, Bilanzgleichung erfüllt, Abgleich mit zweiter Quelle unter 1 Prozent bei Kernwerten |
| 2 Formelregister und Kennzahlen | `metrics.yaml`, `core/registry.py`, Scores aus 3.5 | Jede Kennzahl mit Handrechnung aus einem echten 10-K getestet, Piotroski und Altman für 5 Firmen gegen veröffentlichte Werte geprüft |
| 3 Rechnungslegung und Währung | Regeln ACC-01 bis ACC-14 und 5.2 | Je Regel ein Test mit echtem Bericht, GBX-Fall und ADR-Fall getestet |
| 4 Bewertung | Reverse-DCF, DCF-Szenarien, Multiples, Sensitivität | Lehrbuchbeispiel exakt reproduziert, Property-Tests (höherer WACC ergibt niedrigeren Wert) |
| 5 Universum und Skala | Universum aus 7.1, Scorecards 3.11, Note, Konfidenz, Risiko aus Abschnitt 6 | Alle Unternehmen des Universums haben Note oder Status N mit Grund. Lauf über das ganze Universum ohne Modellaufrufe unter 60 Minuten |
| 6 Daten EU | ESEF, Concept-Mapping, PDF-Rückfall | 10 DAX-Werte vollständig, Abgleich mit Geschäftsbericht von Hand |
| 7 Insider | Form 4, BaFin, Klassifikation | Routinemäßig und opportunistisch für Testpersonen nachvollziehbar korrekt |
| 8 Agenten | A0 bis A10 mit Runner, Schemas und Gates | Einzelanalyse Ende zu Ende, alle Ausgaben schemakonform, alle 14 Abschnitte vorhanden |
| 9 Prüfer | J1 bis J4, Jury, Goldstandard | Mindestwerte aus 11.6 erreicht |
| 10 Start und Kategorie | Skill `/stockagent`, CLI-Dialog, Laufplan, Profile | Alle Startwege aus 9.7 funktionieren, Antworten in `request.json` |
| 11 Portfolio und Bestandsprüfung | Import, Durchschau, Thesenkarten, HOLD-01 bis HOLD-10, Steuerrechnung | Bestandsprüfung für Lucas echte Bestände, Thesenkarten von Luca bestätigt |
| 12 Bericht und Dashboard | Vorlagen aus 12.3, Dashboard aus 13.3 | Snapshot-Tests grün, jede Zahl mit Quelle |
| 13 Betrieb | GitHub Actions, Zeitplan, Benachrichtigung, Papierdepot, Eskalations-Issues | Drei Läufe hintereinander ohne manuellen Eingriff |

### 16.11 GitHub-Repository anlegen

**Voraussetzungen auf Lucas Rechner** (einmalig, Luca führt aus)

1. Git installiert, `git config --global user.name` und `user.email` gesetzt.
2. GitHub CLI installiert und angemeldet (`gh auth login`, Protokoll HTTPS).
3. `uv` installiert.
4. Claude Code installiert und angemeldet.
5. Ein leerer Ordner, etwa `~/Projekte/stockagent`, darin diese Datei als `docs/SPEC.md`.

**Was Claude Code in Phase 0 ausführt**

```bash
cd ~/Projekte/stockagent
git init -b main
uv init --package --python 3.12 --name stockagent
# Struktur aus 16.1 anlegen, .gitignore, .env.example, CLAUDE.md, README.md
uv add pydantic duckdb polars typer questionary jinja2 plotly edgartools xbrl-filings-api claude-agent-sdk
uv add --dev pytest hypothesis ruff mypy pre-commit
uv run pre-commit install
git add -A
git commit -m "chore: Grundgerüst nach SPEC Phase 0"
gh repo create stockagent --private --source=. --remote=origin --push \
  --description "Recherche-Agent für Einzelaktien (privat)"
gh label create escalation --color B60205 --description "Wartet auf Lucas Entscheidung"
gh label create methodology --color 5319E7 --description "Änderung an Formeln oder Gewichten"
for n in $(seq -w 0 13); do gh label create "phase-$n" --color 0E8A16; done
```

Danach setzt Luca die Geheimnisse selbst, damit sie nie im Chatverlauf stehen.

```bash
gh secret set ANTHROPIC_API_KEY
gh secret set DATA_VENDOR_API_KEY
gh secret set SEC_USER_AGENT        # "Vorname Nachname email@beispiel.de"
gh secret set HOLDINGS_AGE_KEY      # nur wenn Läufe in GitHub Actions stattfinden
```

**Regeln für das Repository**

- Sichtbarkeit immer privat.
- `.gitignore` enthält mindestens `.env`, `data/`, `runs/`, `state/holdings*.yaml`, `*.csv` unter `data/`, `.pytr/`.
- Schutzregeln für `main` (Pull Request und grüne CI erforderlich) setzt Claude Code mit `gh api`, sofern Lucas GitHub-Plan sie für private Repositories erlaubt. Im kostenlosen Plan gilt die Regel als Arbeitskonvention. Claude Code pusht nie direkt auf `main`.
- Commit-Nachrichten nach Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `method:` für Methodikänderungen).
- Jede neue Methodik-Version bekommt einen Tag `methodology-vX.Y` und einen Eintrag in `docs/METHODOLOGY_CHANGELOG.md`.
- Pull Requests nutzen eine Vorlage `.github/pull_request_template.md` mit den Feldern Phase, Abnahmekriterien, Testnachweis und Auswirkung auf Noten.

### 16.12 GitHub Actions

| Workflow | Auslöser | Inhalt |
|---|---|---|
| `ci.yml` | Push und Pull Request | ruff, mypy, pytest, Eval-Kurzlauf mit aufgezeichneten Modellantworten (keine API-Kosten) |
| `eval.yml` | Pull Request mit Änderungen in `prompts/`, `agents_src/` oder `config/` | voller Goldstandard-Lauf gegen echte Modelle, Ergebnis als Kommentar am Pull Request, blockiert bei Verschlechterung |
| `scheduled-run.yml` | `cron: "0 4 * * 3"` (Mittwoch 04:00 UTC) und manuell über `workflow_dispatch` mit Eingaben für Kategorie und Tiefe | Hauptlauf. Ein Schritt prüft die ISO-Kalenderwoche und läuft nur in geraden Wochen, weil GitHub-Cron keinen Zwei-Wochen-Takt kennt. GitHub kann geplante Läufe verzögern |
| `daily-light.yml` | `cron: "30 5 * * 1-5"` | Leichtlauf ohne Modellaufrufe, Ereignisprüfung aus 9.2 |

Ergebnisse werden als Workflow-Artefakt hochgeladen (Aufbewahrung 90 Tage) und zusätzlich auf den privaten Branch `reports` committet. GitHub Pages wird nicht genutzt, weil Pages-Seiten auch aus privaten Repositories außerhalb von Enterprise-Plänen öffentlich sind und der Bericht Depotdaten enthält.

### 16.13 Schutz der Depotdaten

Bestände liegen lokal in `state/holdings.yaml` und werden nie im Klartext committet. Laufen Hauptläufe in GitHub Actions, wird die Datei mit `age` verschlüsselt (`state/holdings.yaml.age`) und im Workflow mit dem Secret `HOLDINGS_AGE_KEY` entschlüsselt. Zugangsdaten für Trade Republic verlassen Lucas Rechner nie.

### 16.14 Eskalationen als GitHub-Issues (optional)

Mit `escalations.github_issues: true` legt jeder Lauf für jeden eskalierten Fall ein Issue mit Label `escalation` an. Es enthält die Streitpunkte, beide widersprüchlichen Werte mit Quellen und einen Link auf die Analyse. Luca antwortet mit einem Kommentar in fester Form.

```
/entscheidung annehmen Begründung in einem Satz
/entscheidung ablehnen Begründung in einem Satz
/entscheidung neu-pruefen Was geprüft werden soll
```

Der nächste Lauf liest die Kommentare über `gh api`, speichert die Entscheidung in `decisions` und im Goldstandard und schließt das Issue. So kann der Agent Luca auch zwischen zwei Läufen und vom Handy aus fragen.

---

## 17. Prompt-Bibliothek für Claude Code

### 17.1 Arbeitsweise

- Claude Code immer im Projektordner starten (`cd ~/Projekte/stockagent && claude`).
- Für jede Phase eine neue Sitzung beginnen (`/clear`), damit der Kontext frei von Altlasten ist. Die Spezifikation liegt im Repository und muss nicht neu eingefügt werden.
- Jede Phase im Plan-Modus beginnen (Umschalttaste und Tab, bis "plan mode" angezeigt wird). Claude Code liest, plant und ändert erst nach Lucas Freigabe Dateien.
- Nach jeder Phase einen unabhängigen Prüflauf mit Prompt 17.5 starten.
- Die Prompts sind zum Kopieren gedacht. Text in spitzen Klammern ersetzt Luca.

### 17.2 Prompt 0, Projektstart

```text
Lies docs/SPEC.md vollständig, bevor du irgendetwas tust. Das ist die verbindliche Spezifikation.

Aufgabe: Phase 0 aus Abschnitt 16.10.
1. Fasse in höchstens 15 Stichpunkten zusammen, was du verstanden hast, besonders die harten
   Regeln HR-01 bis HR-16 aus Abschnitt 0.1 und wie jede technisch durchgesetzt wird.
2. Nenne Widersprüche oder Lücken in der Spezifikation, die dich am Bau hindern. Rate nicht.
3. Lege dann nach Abschnitt 16.11 das private GitHub-Repository an, erzeuge die Struktur aus 16.1,
   die CLAUDE.md nach 16.3, die Hooks aus 16.5, das Skript scripts/render_agents.py und die
   Gates aus 12.6 als Module mit Tests. Die Gates dürfen in Phase 0 nur die Grundprüfungen
   enthalten, ihre Tests müssen aber schon die Fälle aus HR-01 bis HR-03 abdecken.
4. Arbeite auf dem Branch phase-00-geruest, committe in kleinen Schritten und öffne am Ende
   einen Pull Request mit der Vorlage. Pushe nie direkt auf main.
5. Setze keine Geheimnisse. Sag mir am Ende, welche gh secret set Befehle ich ausführen muss.
Abgeschlossen ist die Phase erst, wenn alle Abnahmekriterien als Tests grün sind.
```

### 17.3 Prompt-Vorlage für jede weitere Phase

```text
Lies docs/SPEC.md Abschnitt 0.1 und die für Phase <NN> relevanten Abschnitte <Abschnitte>.
Lies CLAUDE.md und docs/METHODOLOGY_CHANGELOG.md.

Aufgabe: Phase <NN> <Name> aus Abschnitt 16.10.
- Erstelle zuerst einen Plan mit Dateien, Funktionen, Tests und den Abnahmekriterien als
  konkrete Testfälle. Warte auf meine Freigabe.
- Schreibe die Tests vor der Implementierung. Jede Formel braucht einen Test mit einer
  Handrechnung aus einem echten Bericht, mit Quelle (Dokument und Seite) im Testkommentar.
- Keine Formel außerhalb von core/registry.py. Keine Zahl aus deinem Vorwissen. Wenn dir
  ein Wert, eine Taxonomie-Bezeichnung oder ein API-Feld unbekannt ist, schlage es in der
  Dokumentation nach oder frag mich.
- Branch phase-<NN>-<kurzname>, kleine Commits, am Ende Pull Request mit Testnachweis.
- Liste am Ende auf, welche Teile der Spezifikation du nicht umgesetzt hast und warum.
```

Die Einträge für `<Abschnitte>` je Phase.

| Phase | Abschnitte |
|---|---|
| 1 Daten USA | 3.2, 7.2, 7.3, 7.5 bis 7.7 |
| 2 Formelregister | 3.3 bis 3.5, 12.2 |
| 3 Rechnungslegung und Währung | 4, 5 |
| 4 Bewertung | 3.6, 5.2 Punkt 6 und 7 |
| 5 Universum und Skala | 3.1, 3.11, 6, 7.1 |
| 6 Daten EU | 7.2, 7.4 |
| 7 Insider | 1 Nr. 1 bis 4, 3.8 |
| 8 Agenten | 8, 12.6, 16.4, 17.6 |
| 9 Prüfer | 11 |
| 10 Start und Kategorie | 9.7 bis 9.9, 16.6 |
| 11 Portfolio und Bestand | 3.10, 9.6, 10 |
| 12 Bericht und Dashboard | 12.3, 12.4, 13 |
| 13 Betrieb | 9.1 bis 9.5, 14, 16.12 bis 16.14 |

### 17.4 Prompts für den Betrieb

**Lauf starten**
```text
/stockagent
```

**Depot prüfen**
```text
/depot-check
Gehe danach jede Position mit einem anderen Ergebnis als "Halten" mit mir einzeln durch.
Zeige Begründung, Belege, Steuerrechnung und was passieren müsste, damit sich die
Einschätzung umkehrt. Triff keine Entscheidung für mich.
```

**Einzelanalyse**
```text
/analyze-stock <ISIN oder Name>
```

**Note erklären**
```text
Erkläre die Note von <Unternehmen> im letzten Lauf. Zeige die Zerlegung in Säulen und
Kennzahl-Perzentile, die Vergleichsgruppe und welche drei Kennzahlen die Note am stärksten
bestimmen. Nutze nur Werte aus runs/<run_id>. Keine eigenen Rechnungen.
```

**Ungereimtheit untersuchen**
```text
Untersuche Ungereimtheit <INC-ID> bei <Unternehmen> aus Lauf <run_id>. Öffne beide Quellen
an den angegebenen Seiten, zitiere die Stellen wörtlich und sag mir, welche Erklärung die
Dokumente stützen. Wenn die Dokumente keine Erklärung liefern, sag das.
```

**Neue Kennzahl**
```text
Füge die Kennzahl <Name> nach Abschnitt 18.1 hinzu. Nenne zuerst die akademische oder
fachliche Quelle der Definition. Schreibe den Test mit Handrechnung aus einem echten Bericht.
Erhöhe methodology_version und ergänze den Changelog. Pull Request mit Label methodology.
```

**Methodik ändern**
```text
Ich möchte <Änderung, etwa Gewicht der Säule Bewertung auf 30 Prozent>. Rechne vor der
Änderung mit dem gespeicherten Datenstand des letzten Laufs, wie sich die Noten verschieben
würden, und zeige die 20 größten Veränderungen. Ändere erst nach meiner Freigabe.
```

**Fehlgeschlagenen Lauf untersuchen**
```text
Der Lauf <run_id> ist fehlgeschlagen oder unvollständig. Lies runs/<run_id>/log.jsonl und
manifest.json, finde die Ursache, reproduziere sie in einem Test und schlage eine Korrektur vor.
```

**Prüferqualität (vierteljährlich)**
```text
Führe eval/run_eval.py aus und vergleiche mit dem letzten Quartal. Zeige Fangquote je
Fehlerart, Fehlalarme, Übereinstimmung der Jury mit meinen Entscheidungen (Cohens Kappa)
und die Zahl der Gate-Vorfälle aus INC-14. Schlage nur Änderungen vor, setze keine um.
```

### 17.5 Prompt für den unabhängigen Prüflauf nach jeder Phase

```text
Starte einen Subagenten ohne Kenntnis unserer bisherigen Unterhaltung. Er soll den Pull
Request <Nummer> gegen docs/SPEC.md prüfen und nur berichten, nicht ändern:
1. Verletzt der Code eine der Regeln HR-01 bis HR-16?
2. Sind alle Abnahmekriterien der Phase durch Tests abgedeckt, die wirklich das Kriterium
   prüfen und nicht nur durchlaufen?
3. Gibt es Formeln außerhalb des Registers, Zahlen ohne Quelle oder Datenzugriffe ohne as_of?
4. Welche Randfälle fehlen (negative Werte, fehlende Perioden, Währungsunterwährungen,
   Restatements)?
Ergebnis als Liste mit Datei, Zeile, Problem und Schweregrad.
```

### 17.6 Pflicht-Präambel für alle Agenten-Prompts

Jede Vorlage in `agents_src/` beginnt mit diesem Block. `scripts/render_agents.py` bricht ab, wenn er fehlt.

```text
Du bist Teil eines Recherche-Systems für Aktien. Für dich gelten ohne Ausnahme diese Regeln:
1. Du schreibst keine Zahlen. Jede Zahl steht als Platzhalter {{kennzahl_id@periode}}.
   Erlaubt sind nur Jahreszahlen, Seitenzahlen und Kennzahl-IDs.
2. Jede Aussage braucht mindestens einen Beleg aus den übergebenen Daten (doc_hash, Seite,
   wörtliches Zitat) oder eine Kennzahl-ID. Eine Aussage ohne Beleg schreibst du nicht.
3. Zitate sind wörtlich und vollständig. Du kürzt oder paraphrasierst sie nicht.
4. Dein Vorwissen über Unternehmen, Märkte und Kurse ist keine Quelle. Du darfst daraus nur
   Fragen ableiten, die du mit den Werkzeugen prüfst.
5. Wenn die Daten eine Frage nicht beantworten, antwortest du mit unknown und nennst den Grund.
   Das ist ein gutes Ergebnis, kein Fehler.
6. Widersprüche zwischen Quellen meldest du als Ungereimtheit mit beiden Stellen. Du entscheidest
   nicht selbst, welche Quelle stimmt.
7. Du gibst keine Kursziele, keine Renditeversprechen und keine Kauf- oder Verkaufsanweisungen.
8. Du antwortest ausschließlich mit JSON nach dem angegebenen Schema.
```

---


---

## 18. Erweiterbarkeit

Das System ist so gebaut, dass Erweiterungen an definierten Stellen andocken.

### 18.1 Neue Kennzahl

1. Eintrag in `config/metrics.yaml` (ID, Formel, Eingaben, Version, Sektorhinweise).
2. Funktion in `core/metrics.py`, registriert über einen Dekorator `@metric("id")`.
3. Test mit Handrechnung.
4. Falls im Score verwendet, Gewicht in `scoring.yaml`, Changelog-Eintrag, `methodology_version` erhöhen.

### 18.2 Neue Datenquelle

Klasse in `data/sources/`, die das Protokoll `DataSource` erfüllt (`fetch(lei, since) -> list[Fact]`, `name`, `priority`). Eintrag in `sources.yaml`. Die Datenqualitätsprüfung behandelt sie automatisch als zusätzliche Quelle.

### 18.3 Neuer Agent

Markdown in `.claude/agents/`, Prompt in `prompts/`, Ein- und Ausgabeschema in `schemas/`, Eintrag im Ablauf von `orchestrator.py`, Goldstandard-Fälle in `eval/`.

### 18.4 Geplante Erweiterungen

| Erweiterung | Nutzen | Aufwand |
|---|---|---|
| Vollständige Normalisierung weiterer Standards (J-GAAP, Ind AS, HGB-Konzern) | Konfidenz K2 auch für diese Unternehmen | mittel je Standard |
| Weitere Scorecards (Biotech mit Pipeline-Bewertung, Rohstoffförderer mit Reserven) | genauere Noten in Sonderbranchen | mittel |
| Transkripte von Analystenkonferenzen | Ton und Aussagen des Managements im Zeitverlauf | mittel, Datenquelle meist kostenpflichtig |
| Konsensschätzungen | Vergleich implizites Wachstum mit Analystenerwartungen | Datenkosten |
| Nachhaltigkeitsdaten aus ESRS-Berichten (CSRD) | Markierung nach Lucas Werten, ohne Einfluss auf die Note | mittel |
| Weitere Länder bei Insider-Daten | Signal für mehr EU-Titel | je Land klein |
| Lernende Gewichte | erst nach 3 Jahren Papierdepot und nur mit getrennter Testperiode | hoch, Risiko der Überanpassung |
| Eigener MCP-Server | Werkzeuge in jeder Claude-Oberfläche | klein |

### 18.5 Versionierung

Jede Ausgabe trägt `methodology_version`, `agent_version`, `prompt_hash` und `model`. Ergebnisse unterschiedlicher Methodik-Versionen werden im Dashboard nie ohne Hinweis verglichen.

---

## 19. Offene Entscheidungen für Luca

| Nr. | Frage | Default im Code |
|---|---|---|
| 1 | Bezieht sich die Zielallokation 60 bis 70 Prozent ETFs auf das Gesamtvermögen oder nur auf Trade Republic? | Gesamtvermögen |
| 2 | Soll der Einzeltitelanteil über neue Sparraten oder auch durch Umschichtung aufgebaut werden? Welche monatliche Sparrate steht zur Verfügung? | nur neue Mittel, Betrag `monthly_contribution_eur` leer |
| 3 | Welche Kategorien soll der Lauf nach Zeitplan abdecken? | Branchenrotation plus beste 5 des Gesamtmarkts plus Depot |
| 4 | Sollen Einzeltitel gezielt Lücken des MSCI World füllen (Small Caps, Schwellenländer)? | neutral |
| 5 | Markierungen nach eigenen Werten (Branchen, Länder), ohne Einfluss auf die Note | keine |
| 6 | Welche Modellanbieter stehen für die Jury zur Verfügung? | nur Claude mit Hinweis im Bericht |
| 7 | Budget für Datenanbieter und Modellkosten pro Monat | 50 EUR |
| 8 | Ausführungsort (lokal, Routine, GitHub Actions) | lokal |
| 9 | Kirchensteuerpflicht für die Steuerrechnung | nein |
| 10 | Eskalationen auch als GitHub-Issues? | ja |
| 11 | Wer ist der Anbieter des Baader-Depots? | offen, nur für Import relevant |

---

## 20. Quellen

**Bewertung und Faktorforschung**
- Nissim, D., Penman, S. (2001). Ratio Analysis and Equity Valuation. Review of Accounting Studies.
- Piotroski, J. (2000). Value Investing. The Use of Historical Financial Statement Information to Separate Winners from Losers. Journal of Accounting Research.
- Altman, E. (1968). Financial Ratios, Discriminant Analysis and the Prediction of Corporate Bankruptcy. Journal of Finance.
- Beneish, M. (1999). The Detection of Earnings Manipulation. Financial Analysts Journal.
- Sloan, R. (1996). Do Stock Prices Fully Reflect Information in Accruals and Cash Flows about Future Earnings? The Accounting Review.
- Novy-Marx, R. (2013). The Other Side of Value. The Gross Profitability Premium. Journal of Financial Economics.
- Asness, C., Frazzini, A., Pedersen, L. (2019). Quality Minus Junk. Review of Accounting Studies.
- McLean, R. D., Pontiff, J. (2016). Does Academic Research Destroy Stock Return Predictability? Journal of Finance 71(1). https://ssrn.com/abstract=2156623
- Bessembinder, H. (2018). Do Stocks Outperform Treasury Bills? Journal of Financial Economics. https://news.wpcarey.asu.edu/20180917-do-stocks-outperform-treasury-bills
- Damodaran, A. Datensätze zu Risikoprämien, Betas und Multiples. https://pages.stern.nyu.edu/~adamodar/

**Insider**
- Cohen, L., Malloy, C., Pomorski, L. (2012). Decoding Inside Information. Journal of Finance 67(3). https://www.nber.org/papers/w16454
- PwC Legal (2026). Neue Meldeschwelle für Directors' Dealings (Art. 19 MAR). https://legal.pwc.de/de/news/fachbeitraege/neue-meldeschwelle-fuer-directors-dealings-art-19-mar
- Heuking (2025). Listing Act, BaFin erhöht Schwellenwert. https://www.heuking.de/de/news-events/newsletter-fachbeitraege/artikel/listing-act-erleichterungen-bei-directors-dealings-bafin-erhoeht-schwellenwert-fuer-transaktionsmeldungen.html

**LLMs in der Finanzanalyse**
- Kim, A., Muhn, M., Nikolaev, V. (2024). Financial Statement Analysis with Large Language Models. Chicago Booth. https://arxiv.org/abs/2407.17866
- Islam, P. et al. (2023). FinanceBench. A New Benchmark for Financial Question Answering. https://arxiv.org/abs/2311.11944
- Xiao, Y. et al. (2025). TradingAgents. Multi-Agents LLM Financial Trading Framework. AAAI 2025 Workshop. https://arxiv.org/abs/2412.20138
- Glasserman, P., Lin, C. (2023). Assessing Look-Ahead Bias in Stock Return Predictions Generated by GPT Sentiment Analysis. https://arxiv.org/abs/2309.17322
- He, S. et al. (2025). Chronologically Consistent Large Language Models. https://arxiv.org/abs/2502.21206

**LLM-as-a-Judge**
- Zheng, L. et al. (2023). Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena. NeurIPS 2023.
- Verga, P. et al. (2024). Replacing Judges with Juries. Evaluating LLM Generations with a Panel of Diverse Models. https://arxiv.org/abs/2404.18796
- Ye, J. et al. (2025). Justice or Prejudice? Quantifying Biases in LLM-as-a-Judge. ICLR 2025. https://arxiv.org/abs/2410.02736
- Shi, L. et al. (2024). Judging the Judges. A Systematic Investigation of Position Bias. https://arxiv.org/abs/2406.07791
- Wataoka, K. et al. (2024). Self-Preference Bias in LLM-as-a-Judge. https://arxiv.org/abs/2410.21819
- Li, H. et al. (2024). LLMs-as-Judges. A Comprehensive Survey. https://arxiv.org/abs/2412.05579
- Zhuge, M. et al. (2025). Agent-as-a-Judge. Evaluate Agents with Agents. ICML 2025. https://arxiv.org/abs/2410.10934
- Li, Z. et al. (2026). MARCH. Multi-Agent Reinforced Self-Check for LLM Hallucination. ACL 2026. https://arxiv.org/abs/2603.24579

**Rechnungslegung, Währung, Liquidität, Größe**
- Ball, R. (2006). International Financial Reporting Standards (IFRS). Pros and Cons for Investors. Accounting and Business Research.
- Leuz, C., Nanda, D., Wysocki, P. (2003). Earnings Management and Investor Protection. Journal of Financial Economics.
- Daske, H., Hail, L., Leuz, C., Verdi, R. (2008). Mandatory IFRS Reporting around the World. Journal of Accounting Research. https://repository.upenn.edu/handle/20.500.14332/1111
- Barth, M., Landsman, W., Lang, M. (2008). International Accounting Standards and Accounting Quality. Journal of Accounting Research.
- Lev, B., Sougiannis, T. (1996). The Capitalization, Amortization, and Value-Relevance of R&D. Journal of Accounting and Economics.
- IASB (2024). IFRS 18 Presentation and Disclosure in Financial Statements. Zusammenfassung BDO. https://www.bdo.com.au/en-au/blogs/corporate-reporting/ifrs-18-is-here
- Adler, M., Dumas, B. (1984). Exposure to Currency Risk. Definition and Measurement. Financial Management.
- Jorion, P. (1990). The Exchange-Rate Exposure of U.S. Multinationals. Journal of Business.
- Bartov, E., Bodnar, G. (1994). Firm Valuation, Earnings Expectations, and the Exchange-Rate Exposure Effect. Journal of Finance.
- Damodaran, A. Investment Valuation (Lehrbuch), Kapitel zu Währungen und Finanzdienstleistern.
- Amihud, Y., Mendelson, H. (1986). Asset Pricing and the Bid-Ask Spread. Journal of Financial Economics.
- Amihud, Y. (2002). Illiquidity and Stock Returns. Cross-Section and Time-Series Effects. Journal of Financial Markets.
- Fama, E., French, K. (2008). Dissecting Anomalies. Journal of Finance.
- Hou, K., Xue, C., Zhang, L. (2020). Replicating Anomalies. Review of Financial Studies.

**Skala und Sektor-Scorecards**
- Mohanram, P. (2005). Separating Winners from Losers among Low Book-to-Market Stocks Using Financial Statement Analysis. Review of Accounting Studies. https://ideas.repec.org/a/spr/reaccs/v10y2005i2d10.1007_s11142-005-1526-4.html
- Calomiris, C., Nissim, D. (2014). Crisis-Related Shifts in the Market Valuation of Banking Activities. Journal of Financial Intermediation. Vorfassung "Activity-Based Valuation of Bank Holding Companies". https://business.columbia.edu/sites/default/files-efs/pubfiles/3307/Activity%20Based%20Valuation%20of%20Bank%20Holding%20Companies.pdf
- Nissim, D. (2010). Analysis and Valuation of Insurance Companies. Columbia Business School, CEASA. https://business.columbia.edu/faculty/people/doron-nissim
- Asness, C., Moskowitz, T., Pedersen, L. (2013). Value and Momentum Everywhere. Journal of Finance.
- Ang, A., Hodrick, R., Xing, Y., Zhang, X. (2006). The Cross-Section of Volatility and Expected Returns. Journal of Finance.
- Frazzini, A., Pedersen, L. (2014). Betting Against Beta. Journal of Financial Economics.
- Koller, T., Goedhart, M., Wessels, D. Valuation. Measuring and Managing the Value of Companies (McKinsey).

**Bestandsprüfung und Verkaufsverhalten**
- Shefrin, H., Statman, M. (1985). The Disposition to Sell Winners Too Early and Ride Losers Too Long. Journal of Finance.
- Odean, T. (1998). Are Investors Reluctant to Realize Their Losses? Journal of Finance. https://faculty.haas.berkeley.edu/odean/papers/disposition/disposition.html
- Barber, B., Odean, T. (2000). Trading Is Hazardous to Your Wealth. Journal of Finance.
- Kaminski, K., Lo, A. (2014). When Do Stop-Loss Rules Stop Losses? Journal of Financial Markets.

**Reproduzierbarkeit und Halluzinationen**
- Anthropic. Reduce hallucinations. https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations
- Atil, B. et al. (2024). LLM Stability. A Detailed Analysis with Some Surprises. https://arxiv.org/abs/2408.04667
- He, H., Thinking Machines Lab (2025). Defeating Nondeterminism in LLM Inference. https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/
- Wang, X. et al. (2023). Self-Consistency Improves Chain of Thought Reasoning in Language Models. ICLR 2023.

**Daten und Werkzeuge**
- SEC EDGAR APIs. https://www.sec.gov/edgar/sec-api-documentation
- filings.xbrl.org und xbrl-filings-api. https://filings.xbrl.org/about.html , https://pypi.org/project/xbrl-filings-api
- pytr (inoffiziell). https://github.com/pytr-org/pytr
- Trade Republic Handelsplätze 2026. https://brokerexperte.de/traderepublic-erfahrungsbericht/ , https://www.dasinvestment.com/trade-republic-lang-schwarz-analyse/
- Claude Code Subagents. https://code.claude.com/docs/en/sub-agents
- Claude Code Routines. https://code.claude.com/docs/en/routines
- Claude Code Hooks. https://code.claude.com/docs/en/hooks-guide
- Claude Code Skills. https://code.claude.com/docs/en/skills
- Claude Code Headless und Agent SDK. https://code.claude.com/docs/en/headless
- GitHub CLI. https://cli.github.com/manual/

---

*Dieses Dokument ist eine technische Spezifikation für ein Recherche-Werkzeug. Es enthält keine Anlageberatung. Rechtliche und steuerliche Angaben entsprechen dem recherchierten Stand Oktober 2026 und sind vor Verwendung zu prüfen.*
