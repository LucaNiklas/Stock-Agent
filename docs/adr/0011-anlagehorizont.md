# ADR 0011: Anlagehorizont und Säule Momentum

Status: angenommen (21.10.2026, Lucas Vorgabe: „Aktien ein paar Monate bis eben Jahre halten,
1 bis 5 Jahre, 15 bis 20 Jahre ist mein Horizont für ETFs. Gerne mit Filterfunktion.“)

## Kontext

Die Methodik war auf sehr lange Haltedauer ausgelegt (SPEC 3.1 nannte 15 bis 20 Jahre, A7 fragte
nach dem Scheitern über 5 bis 10 Jahre). Für einige Monate bis wenige Jahre gilt in der Forschung:
Kursmomentum über 3 bis 12 Monate sagt die Rendite der folgenden Monate voraus (Jegadeesh und
Titman 1993), ebenso die Kursreaktion auf Berichte (Bernard und Thomas 1989; Chan, Jegadeesh und
Lakonishok 1996). Bewertung und Qualität wirken langsamer, über mehrere Jahre (Asness, Moskowitz
und Pedersen 2013; Asness, Frazzini und Pedersen 2019). Günstige Titel mit fallendem Kurs bleiben
oft über Monate günstig.

## Entscheidung

1. **Gleiche Rechnung für alle Horizonte.** Kennzahlen, Rechenwege, DCF, Prüfpunkte, Kappungen,
   Konfidenz und Risiko ändern sich nicht.
2. **Neue Säule Momentum** (`core/momentum.py`, Kennzahlen in `config/horizonte.yaml`):
   Momentum 12-1 und 6-1, Nähe zum 52-Wochen-Hoch, Abstand zur 200-Tage-Linie, Kursreaktion auf den
   letzten Bericht (höchstens 120 Tage alt), Umsatzwachstum des letzten Jahres, Veränderung der
   EBIT-Marge. Kurse in EUR, Rang in derselben Vergleichsgruppe wie die übrigen Säulen.
3. **Gewicht je Horizont:** kurz (Monate bis 1 Jahr) 40 %, mittel (1 bis 5 Jahre) 15 %, lang
   (über 5 Jahre) 0 %. Die übrigen Säulen behalten ihr Verhältnis (auch eigene Gewichte einer
   Scorecard). Vorab festgelegt, nicht an Daten angepasst.
4. **Standardhorizont mittel.** Die Hauptnote (`grades.grade`, Notenkontrolle) ist die des
   Horizonts mittel, entsprechend Lucas Haltedauer. Die Noten aller Horizonte stehen in
   `grades.detail_json` und im Tagesstand (`grade_snapshots.horizonte_json`, Schema 11).
5. **Kategorie im Horizont kurz:** Attraktiv nur mit Momentum-Säule mindestens 50, sonst
   Beobachten mit Grund.
6. **Bedienung:** Dashboard mit Auswahl des Horizonts (gemerkt im Browser), Filter nach Note und
   Kategorie des gewählten Horizonts, Sortierung nach Gesamtwert, Noten aller Horizonte in der
   Detailansicht, CSV mit einer Spalte je Horizont. Freitext: „kurzfristig“, „1 bis 5 Jahre“,
   „langfristig“. Terminal: `stockagent screen --horizont kurz --note A,B`.
7. **A7 Gegenposition** betrachtet die Haltedauer Monate bis 5 Jahre (Vorlage 1.1.0).
8. **Trading-Skills** (Paket vom 20.10.2026): keiner installiert (brauchen den bezahlten
   FMP-Dienst, planen Positionsgrößen und Orders, HR-09 und HR-15). Übernommen als Idee, gebaut
   aus eigenen Daten: Kursreaktion auf Berichte (pead-screener, earnings-trade-analyzer), Lage zur
   200-Tage-Linie (earnings-trade-analyzer). Die Methodik von backtest-expert dient der
   Notenkontrolle je Horizont.

## Folgen und offen

- Firmen ohne ein volles Jahr Kurse oder ohne frischen Kurs haben kein Kursmomentum: geringere
  Abdeckung, im Horizont kurz greift dann eher die Kappung „Abdeckung gering“.
- Die Kursreaktion ist eine Rohrendite ohne Marktindex. Gewinnüberraschungen gegen
  Analystenschätzungen gibt es ohne eigene Quelle nicht.
- Der Goldstandard-Lauf für die geänderte A7-Vorlage folgt mit Bauschritt 10 (eval noch
  Platzhalter).
- Notenkontrolle je Horizont (SPEC 14.3) misst ab jetzt mit. Ob 40 % und 15 % passen, zeigt sie
  frühestens nach 12 Monaten. Eine Änderung wäre eine neue Methodik-Version.
