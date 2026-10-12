"""Annahme von Agentenausgaben.

PLATZHALTER: wird in Bauschritt 6 gebaut (docs/BAUPLAN.md).
Inhalt: Prüft jede Ausgabe gegen ihr Schema und alle Gates in fester Reihenfolge (SPEC 12.6),
schickt Abgelehnte höchstens zweimal mit Fehlermeldung zurück, dann `escalated`. Protokolliert
Modell, Dauer und Tokens in `log.jsonl`.
"""
