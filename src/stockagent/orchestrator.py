"""Zustandsautomat der Tiefenanalyse (SPEC 15.1).

PLATZHALTER: wird in Bauschritt 6 gebaut (docs/BAUPLAN.md).
Inhalt: `stockagent next <run_id>` nennt den nächsten erlaubten Schritt (welcher Agent, welche
Eingabedatei, wohin die Ausgabe), `stockagent accept <run_id> <datei>` nimmt eine Ausgabe an.
Erzwingt Reihenfolge, Blindheit von J1 (HR-14) und Grenzen (HR-18), kann abgebrochene Läufe
fortsetzen.
"""
