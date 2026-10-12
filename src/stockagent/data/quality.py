"""Datenqualitätsprüfungen (SPEC 3.2).

PLATZHALTER: wird in Bauschritt 2 gebaut (docs/BAUPLAN.md).
Inhalt: Bilanzgleichung je Periode (Toleranz 0,5 Prozent), XBRL-Summenstruktur, Einheiten und
Skalierung, Periodenlogik und TTM ohne Doppelzählung, Abgleich zweier Quellen, Ausreißer über
Median und MAD, Restatements erkennen, Aktienanzahl um Splits bereinigen. Ergebnis sind
`dq_flags` je Unternehmen, die die Konfidenz bestimmen.
"""
