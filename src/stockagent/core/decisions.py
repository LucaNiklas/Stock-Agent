"""Kategorie und Zustandsautomat (SPEC 6.5, HR-13).

PLATZHALTER: wird in Bauschritt 5 gebaut (docs/BAUPLAN.md).
Inhalt: Deterministische Kategorie (Attraktiv, Beobachten, Neutral, Unattraktiv, Eskaliert,
Nicht bewertbar), Hysterese über zwei Läufe (9.5). Sprachmodelle haben nur die Übergänge
`downgrade` und `escalate`.
"""
