"""Auswertung J1 Zahlenprüfer (SPEC 11.2).

PLATZHALTER: wird in Bauschritt 6 gebaut (docs/BAUPLAN.md).
Inhalt: Vergleicht J1-Ergebnisse mit den Werten der Agenten erst nach J1s Rechnung: Toleranz 0,5
Prozent `match`, bis 2 Prozent `rounding`, darüber `mismatch`. Ein `mismatch` bei einer
Kernkennzahl eskaliert.
"""
