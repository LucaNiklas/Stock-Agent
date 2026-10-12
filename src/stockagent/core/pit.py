"""Zeitpunktbezug (Point-in-Time, SPEC 7.5, HR-07).

PLATZHALTER: wird in Bauschritt 2 gebaut (docs/BAUPLAN.md).
Inhalt: Reine Funktionen: aus allen Fassungen eines Werts die zum Analysedatum gültige wählen
(`published_at <= as_of`, Restatements erst ab ihrem Datum). Wird von
`store.pit_query(as_of=...)` genutzt.
"""
