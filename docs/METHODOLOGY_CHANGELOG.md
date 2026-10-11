# Methodik-Changelog

Jede Methodikänderung hier eintragen und methodology_version erhöhen.

## 4.0 (09.10.2026)

- Umfang auf Anzeigen und Bewerten begrenzt, Portfolio, Bestand und Steuer in Anhang A zurückgestellt.
- Kategorie "Kaufkandidat" ersetzt durch "Attraktiv", Bewertungsbedingung nur aus deterministischen Größen (Reverse-DCF, Multiples).
- DCF-Annahmen als Stufen aus der Historie statt freier Zahlen.
- K1 und K2 hängen nicht mehr an einer Tiefenanalyse.
- Reverse-DCF auf Umsatzbasis bei negativem FCF.

## 4.1 (11.10.2026)

- Agenten laufen über das Claude-Abo, Ablauf vom Python-Zustandsautomaten vorgegeben.
- Modellzuordnung je Agent (Haiku, Sonnet, Opus, optional Gemini) in config/models.yaml.
- A9 Synthese-Agent wieder in Abschnitt 8.3 (war bei Version 4.0 versehentlich im Anhang).
