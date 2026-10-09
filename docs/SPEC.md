# Stock-Agent: Spezifikation (Version 4.0, Stand 09.10.2026)

Recherche- und Bewertungssystem für Aktien, die bei Trade Republic handelbar sind. Nur Anzeigen und Bewerten, keine Orders, keine Depot- oder Budgetplanung.

Die Spezifikation ist in eine Datei je Hauptabschnitt aufgeteilt, damit jede Sitzung nur die Abschnitte liest, die der aktuelle Bauschritt braucht (Tabelle in 17.3). Abschnitt 0 ist immer zu lesen.

| Abschnitt | Datei |
|---|---|
| 0. Arbeitsanweisung, Umfang und harte Regeln | [00-arbeitsanweisung.md](spec/00-arbeitsanweisung.md) |
| 1. Was am Vorgängerdokument falsch, veraltet oder unvollständig war | [01-korrekturen-vorgaengerversionen.md](spec/01-korrekturen-vorgaengerversionen.md) |
| 2. Zweck und Umfang | [02-zweck-und-umfang.md](spec/02-zweck-und-umfang.md) |
| 3. Bewertungsmethodik | [03-bewertungsmethodik.md](spec/03-bewertungsmethodik.md) |
| 4. Unterschiede in der Rechnungslegung | [04-unterschiede-in-der-rechnungslegung.md](spec/04-unterschiede-in-der-rechnungslegung.md) |
| 5. Währungen | [05-waehrungen.md](spec/05-waehrungen.md) |
| 6. Bewertungsskala | [06-bewertungsskala.md](spec/06-bewertungsskala.md) |
| 7. Datenquellen und Datenschicht | [07-datenquellen-und-datenschicht.md](spec/07-datenquellen-und-datenschicht.md) |
| 8. Agentenarchitektur | [08-agentenarchitektur.md](spec/08-agentenarchitektur.md) |
| 9. Ablauf eines Laufs | [09-ablauf-eines-laufs.md](spec/09-ablauf-eines-laufs.md) |
| 10. Bestandsprüfung und Verkaufslogik | [10-bestandspruefung-und-verkaufslogik.md](spec/10-bestandspruefung-und-verkaufslogik.md) |
| 11. Verifikationssystem (LLM-as-a-Judge) | [11-verifikationssystem-llm-as-a-judge.md](spec/11-verifikationssystem-llm-as-a-judge.md) |
| 12. Standardisiertes Analyseformat und Reproduzierbarkeit | [12-analyseformat-und-reproduzierbarkeit.md](spec/12-analyseformat-und-reproduzierbarkeit.md) |
| 13. Nachvollziehbarkeit und Darstellung | [13-nachvollziehbarkeit-und-darstellung.md](spec/13-nachvollziehbarkeit-und-darstellung.md) |
| 14. Backtesting und Notenkontrolle | [14-backtesting-und-notenkontrolle.md](spec/14-backtesting-und-notenkontrolle.md) |
| 15. Technische Grundsatzentscheidung | [15-technische-grundsatzentscheidung.md](spec/15-technische-grundsatzentscheidung.md) |
| 16. Umsetzung mit Claude Code im Detail | [16-umsetzung-mit-claude-code-im-detail.md](spec/16-umsetzung-mit-claude-code-im-detail.md) |
| 17. Prompt-Bibliothek für Claude Code | [17-prompt-bibliothek-fuer-claude-code.md](spec/17-prompt-bibliothek-fuer-claude-code.md) |
| 18. Erweiterbarkeit | [18-erweiterbarkeit.md](spec/18-erweiterbarkeit.md) |
| 19. Offene Entscheidungen für Luca | [19-offene-entscheidungen-fuer-luca.md](spec/19-offene-entscheidungen-fuer-luca.md) |
| 20. Quellen | [20-quellen.md](spec/20-quellen.md) |
| Anhang A. Zurückgestellte Module aus Version 3 | [anhang-a-zurueckgestellt.md](spec/anhang-a-zurueckgestellt.md) |

*Dieses Dokument ist eine technische Spezifikation für ein Recherche-Werkzeug. Es enthält keine Anlageberatung. Rechtliche und steuerliche Angaben entsprechen dem recherchierten Stand Oktober 2026 und sind vor Verwendung zu prüfen.*
