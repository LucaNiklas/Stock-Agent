# ADR 0003: Vier Abteilungen und Quellenkarte

Status: angenommen (13.10.2026, Entscheidung Luca)

## Kontext

Bis Version 4.1 waren die Agenten eine lange Liste (A0 bis A9, J1 bis J4, F1), und A1 sollte fehlende Dokumente frei per Websuche finden. Luca wollte, dass

- die Recherche einen klaren Arbeitsablauf hat und der zuständige Agent genau weiß, wo er welche Information findet,
- Recherche, Berechnung und Auswertung als getrennte Abteilungen arbeiten.

Als Ausgangspunkt diente der Bericht von Anthropic über sein Recherchesystem mit mehreren Agenten (https://www.anthropic.com/engineering/multi-agent-research-system, gelesen am 13.10.2026). Die für uns relevanten Befunde:

- Ein Leit-Agent plant und verteilt Teilaufgaben an parallele Arbeiter. Jede Teilaufgabe braucht Ziel, Ausgabeformat, Werkzeuge und Quellen sowie Grenzen, sonst entsteht doppelte Arbeit.
- Der Aufwand muss zur Aufgabe passen (einfache Faktensuche: 1 Agent, 3 bis 10 Werkzeugaufrufe). Ohne Regeln starteten frühe Versionen 50 Subagents für einfache Fragen.
- Mehrere Agenten brauchen etwa 15-mal so viele Tokens wie ein Chat. Das lohnt sich nur bei breiten, unabhängigen Teilaufgaben.
- Ergebnisse gehen als Dateien weiter, nur Verweise wandern zwischen den Agenten.
- Agenten bevorzugten ohne Vorgaben SEO-Seiten vor amtlichen Quellen.
- Für die erste Evaluation reichen etwa 20 echte Fälle.

## Entscheidung

1. Vier Abteilungen (SPEC 8.1): Recherche, Berechnung, Auswertung und Aufbereitung, Prüfung. Jede hat eigene Werkzeugrechte und übergibt nur ein Artefakt als Datei (Dossier, Rechenergebnisse, Bericht). Die Berechnung ist reines Python ohne Sprachmodell.
2. Quellenkarte `config/source_map.yaml` (SPEC 8.9): Je Information und Region die Quellen in fester Reihenfolge, mit Zugriff `python` oder `agent`. Was eine feste Adresse hat (SEC, GLEIF, ESEF, OpenFIGI), holt Python. Agenten suchen nur dort, wo es keine feste Adresse gibt, und nur auf den Domains des Eintrags.
3. Feste Auftragsform mit vier Teilen und Aufwandsgrenzen je Auftragsart in `config/models.yaml` (SPEC 8.10). Die Aufträge erzeugt der Zustandsautomat.
4. Kein Leit-Agent als Subagent: In Claude Code starten Subagents keine weiteren Subagents. Die Leitung liegt beim Zustandsautomaten (Plan) und der Hauptsitzung (Ausführung, parallele Aufrufe).
5. Fehlt der Auswertung eine Information, stellt sie eine Nachforderung an die Recherche (höchstens eine Runde), statt selbst zu suchen.
6. Goldstandard beginnt mit mindestens 20 Fällen aus 5 Unternehmen (SPEC 11.6).

## Folgen

- Bauschritt 2 baut den Python-Teil der Recherche für die USA und die erste Fassung der Quellenkarte. Der Rechenweg `core/calc.py` wird dafür aus Schritt 3 vorgezogen, weil schon die Datenqualitätsprüfungen rechnen (HR-06, HR-19).
- Bauschritt 6 setzt die Werkzeugrechte je Abteilung im Frontmatter der Agenten um und baut das Dossier und die Nachforderung in den Zustandsautomaten ein.
- Ein Test prüft, dass jedes Quellenmodul in der Quellenkarte steht und umgekehrt.
