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
- Ablauf. J1 bekommt die Liste aller quantitativen Claims, aber ohne die vom Agenten genannten Werte. Er bestimmt jeden Wert selbst aus `facts` und Skripten und prüft dabei den Rechenweg Schritt für Schritt mit seinen Prüfpunkten (12.7). Erst danach vergleicht der Orchestrator.
- Toleranz. Relative Abweichung bis 0,5 Prozent gilt als Übereinstimmung, bis 2 Prozent als Rundung (Warnung), darüber als Fehler.
- Ergebnis je Claim. `match`, `rounding`, `mismatch`, `not_computable`.
- Ein einziger `mismatch` bei einer Kernkennzahl setzt den Kandidaten auf `escalated`.

**Ebene 2, J2 Belegprüfer (Groundedness).**
- Ablauf. Jede qualitative Behauptung wird gegen die zitierte Stelle geprüft. J2 liest die Seite selbst und beantwortet je Claim "Wird die Aussage von der Stelle gedeckt?" mit `supported`, `partially`, `not_supported`, `contradicted`.
- Behauptungen ohne Beleg werden gestrichen, nicht nachträglich belegt.
- Modell nach 8.7. Bevorzugt Gemini als andere Modellfamilie als A3 und A4, sonst Sonnet mit eigenem Prompt und verborgener Herkunft der Texte.

**Ebene 3, J3 Jury.**
- Drei Richter: Opus, Sonnet und Gemini (8.7, 8.8). Ist Gemini nicht verfügbar, ersetzt Haiku den dritten Platz mit eigener Rubrik-Perspektive, und der Bericht weist darauf hin, dass die Diversität eingeschränkt ist.
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

Eskaliert wird bei `mismatch` in Kernkennzahlen, `contradicted` bei einer Behauptung, uneiniger Jury, Forensik-Flag ohne Entkräftung, Datenwiderspruch über 5 Prozent und Stopp-Flags bei Titeln der Beobachtungsliste. Eskalierte Fälle erscheinen im Dashboard in einer eigenen Warteschlange mit den konkreten Streitpunkten. Lucas Entscheidung (`human_decision`, `human_note`) wird gespeichert und fließt in den Goldstandard.

### 11.6 Kalibrierung der Prüfer

1. Goldstandard-Datensatz in `eval/gold/`. Start mit mindestens 20 Fällen aus 5 Unternehmen, für die Luca Kernkennzahlen aus den Originalberichten händisch prüft. Kleine Stichproben reichen am Anfang, weil Verbesserungen an Prompts große Effekte haben (Vorbild Anthropic, 8.1). Später auf 20 Unternehmen erweitern. Dazu absichtlich fehlerhafte Analysen (falsche Zahl, falsche Periode, erfundene Aussage, fehlender Risikofaktor), um die Fangquote zu messen.
2. Metriken. Fangquote je Fehlerart, Fehlalarmquote, Übereinstimmung Jury mit Luca (Cohens Kappa), Stabilität bei Wiederholung.
3. Mindestanforderung vor Produktivbetrieb. J1 findet mindestens 95 Prozent der eingebauten Zahlenfehler, J2 mindestens 85 Prozent der erfundenen Aussagen.
4. Jede Prompt- oder Modelländerung läuft gegen den Goldstandard. Verschlechterungen blockieren die Änderung (Test in der CI).
