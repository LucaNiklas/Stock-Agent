"""EU-Abschlussdaten aus ESEF-Berichten (SPEC 7.2).

PLATZHALTER: wird in Bauschritt 7 Teil 2 gebaut, sobald die Domain `filings.xbrl.org` in der
Umgebung freigegeben ist (am 20.10.2026 von der Netzwerkrichtlinie gesperrt, ADR 0009).
Inhalt: ESEF-Inline-XBRL über filings.xbrl.org (xBRL-JSON je Einreichung, Suche über die LEI aus
der GLEIF), Abdeckung ab Geschäftsjahr 2020, Werte als `facts` mit `issuer_id = lei:<LEI>`.
Die IFRS-Konzeptzuordnung steht schon in `config/concept_map.yaml` (geprüft an 20-F-Berichten).
Anhangangaben fehlen meist strukturiert, dafür der PDF-Rückfall (SPEC 7.4) mit A2.
"""
