# ADR 0005: Kursquelle Yahoo und Bewertung auf Anfrage

Status: angenommen (14.10.2026, Entscheidung Luca)

## Kontext

Bauschritt 4 braucht Börsenkurse: für Börsenwert, Unternehmenswert, KGV, EV/EBIT,
FCF-Rendite und die Einordnung gegen die eigene Geschichte über 10 Jahre (SPEC 3.3, 3.6). Das
Universum hat 14.509 Aktien: 3.351 aus den USA, 4.671 aus Europa, 2.342 aus Kanada, 1.881 aus
Asien und 1.043 aus Australien (Land des Hauptsitzes, Stand 13.10.2026).

Geprüfte Quellen (14.10.2026, nur über Suchergebnisse, die Anbieterseiten waren im Netz dieser
Umgebung nicht erreichbar):

| Quelle | Gratis | Bewertung |
|---|---|---|
| Polygon.io / Massive | 5 Abrufe je Minute, 2 Jahre, nur USA, alle US-Aktien eines Tages in einem Abruf | offiziell, aber nur USA und zu kurze Geschichte |
| Alpha Vantage | 25 Abrufe am Tag | zu wenig, MCP-Server ändert daran nichts |
| Financial Modeling Prep | 250 Abrufe am Tag, gratis vermutlich nur USA | kein Vorteil gegenüber Polygon |
| Tiingo | 500 Titel im Monat | zu wenige |
| Twelve Data | 800 Abrufe am Tag, Europa bezahlt | zu langsam für viele Titel |
| EODHD | 20 Abrufe am Tag, bezahlt weltweit | Option für später |
| Stooq | Schlüssel per Captcha seit April 2026, Tageskontingent unbekannt | gut für US, DE, UK, PL, sonst lückenhaft |
| Deutsche Börse (AWS Open Data) | als veraltet markiert | keine Quelle |
| Yahoo Finance | ohne Schlüssel, weltweit, lange Geschichte | inoffiziell, laut Yahoo nur persönliche Nutzung, kann jederzeit ausfallen |

Luca fragt selbst höchstens etwa 50 Titel am Tag ab und braucht die Bewertung nur für Titel,
die er anfragt (Gespräch vom 14.10.2026).

## Entscheidung

1. **Bewertung auf Anfrage statt Gesamtlauf.** Das System bewertet nur angefragte Titel und
   ihre Vergleichsgruppe. Filter nach Land, Branche, Stufe und Größe nach Umsatz brauchen keine
   Kurse. Die Filter Note, Konfidenz und Risiko zeigen die schon bewerteten Titel. Ein Knopf
   „Alle bewerten“ bleibt für später möglich.
2. **Vergleichsgruppe höchstens 50 Titel** (Lucas Vorgabe), mindestens 15 wie bisher (SPEC 6.2).
   Hat die Branche mehr, nimmt das System die 50 mit dem ähnlichsten Umsatz, weil der Umsatz
   ohne Kurs bekannt ist. Kurse der Vergleichsgruppe werden gespeichert und erst nach einer
   Woche erneuert (`config/scoring.yaml`, Schritt 5).
3. **Yahoo Finance als einzige Kursquelle** für alle Länder. Abgerufen wird die Chart-Adresse,
   die auch die Bibliothek yfinance nutzt, aber mit einem eigenen kleinen Modul
   (`data/sources/yahoo.py`):
   - eigener User-Agent, keine Nachahmung eines Browsers, kein Umgehen eines Schutzes. Lehnt
     Yahoo das ab, wird es gemeldet und nicht umgangen;
   - jede Antwort unverändert in `data/raw/` mit SHA-256 (HR-12, SPEC 7.6);
   - keine zusätzlichen Bibliotheken (yfinance zieht pandas und eine Browser-Nachahmung mit);
   - Pause zwischen Abrufen, beim ersten Mal 10 Jahre, danach nur die letzten Monate, höchstens
     einmal am Tag je Titel;
   - abschaltbar in `config/sources.yaml`. Andere Nutzer (SPEC 18.6) schalten die Quelle
     selbst ein und stimmen damit Yahoos Bedingungen für sich zu.
4. **Zuordnung ISIN zu Yahoo-Symbol** über OpenFIGI (ADR 0002): alle Notierungen der ISIN, in
   der Reihenfolge Heimatbörse, USA, Xetra, Frankfurt. Ein Symbol gilt nur, wenn Yahoo eine
   Aktie meldet und der Name zum Börsennamen passt. Sonst bleibt der Titel ohne Kurs, mit
   Grund. Lucas Zuordnungen in `state/price_symbols.yaml` haben Vorrang
   (`stockagent prices map`).
5. **Kurse werden wie geliefert gespeichert:** Schlusskurs (um Splits bereinigt), bereinigter
   Schlusskurs, Volumen, Währung wie geliefert (auch GBp), Splits als Zähler und Nenner,
   Dividenden. Umrechnungen rechnet `core/fx.py` über den Rechenweg (HR-06).

## Folgen

- Kein API-Schlüssel nötig, aber die Domains `query1.finance.yahoo.com` und
  `query2.finance.yahoo.com` müssen in der Netzwerkfreigabe stehen.
- Fällt Yahoo aus, fehlen Kurse. Titel ohne Kurs bekommen keine Bewertungskennzahlen, die
  übrigen Kennzahlen bleiben. Polygon ist als zweite Quelle für US-Kurse vorgesehen, falls sich
  Yahoo als unzuverlässig erweist (Gegenprobe, CP-04).
- Es gibt keine Gegenprobe der Kurse aus einer zweiten Quelle. Plausibilitätsprüfungen
  (positive Kurse, Währung, veralteter letzter Kurs) fangen grobe Fehler ab.
- Kurse für Europa und Asien sind sofort verfügbar, Bewertungen dort aber erst mit den
  Abschlusszahlen (Europa ab Schritt 7, Asien ohne Plan).
- Die Einordnung „gegen den Gesamtmarkt“ (SPEC 3.3) entfällt, solange es keinen Gesamtlauf
  gibt. Die Notenkontrolle (SPEC 14.2) misst die bewerteten Titel.
