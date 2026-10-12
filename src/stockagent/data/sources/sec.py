"""Anbindung SEC EDGAR.

PLATZHALTER: wird in Bauschritt 2 gebaut (docs/BAUPLAN.md).
Inhalt: Mit `edgartools`: `company_tickers.json` (CIK, Ticker), Submissions (Name, SIC-Code,
Geschäftsadresse, Gründungsstaat, Liste der Einreichungen), Company Facts (XBRL-Werte mit
Konzept, Periode, Einheit, Einreichungsdatum). User-Agent aus `SEC_USER_AGENT` in `.env`,
höchstens 10 Anfragen je Sekunde, Rohdaten über `rawstore`. In Schritt 9 kommt Form 4 (Insider)
dazu.
"""
