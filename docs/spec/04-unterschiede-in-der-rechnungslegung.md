## 4. Unterschiede in der Rechnungslegung

### 4.1 Warum das System normalisiert

Zwei gleich benannte Kennzahlen aus verschiedenen Standards messen oft Verschiedenes. Die Forschung zeigt außerdem, dass derselbe Standard je nach Land unterschiedlich angewandt wird.

| Befund | Quelle | Folgerung |
|---|---|---|
| IFRS-Einführung bedeutet keine einheitliche Praxis. Anreize der Unternehmen und Durchsetzung im Land bestimmen die tatsächliche Bilanzierung | Ball (2006, Accounting and Business Research) | Standardname allein reicht nicht für Vergleichbarkeit |
| Ergebnisglättung und Bilanzpolitik sind in Ländern mit schwachem Anlegerschutz systematisch stärker | Leuz, Nanda und Wysocki (2003, Journal of Financial Economics) | Landesumfeld als Information im Bericht |
| Kapitalmarkteffekte der verpflichtenden IFRS-Einführung zeigen sich vor allem dort, wo Durchsetzung stark ist | Daske, Hail, Leuz und Verdi (2008, Journal of Accounting Research) | Konfidenz hängt nicht nur am Standard |
| Unternehmen mit IAS/IFRS zeigen weniger Ergebnisglättung und zeitnähere Verlustausweise als unter lokalen Standards | Barth, Landsman und Lang (2008, Journal of Accounting Research) | IFRS und US-GAAP als Kernstandards, lokale Standards mit Abschlag |
| Umformulierung der Abschlüsse in operative und finanzielle Teile macht Unternehmen über Standards hinweg vergleichbar | Nissim und Penman (2001), Penman (Lehrbuch) | Das System rechnet Zwischensummen selbst aus Komponenten |
| Aktivierte F&E-Ausgaben sind wertrelevant | Lev und Sougiannis (1996, Journal of Accounting and Economics) | Beide Varianten (aktiviert und aufwandswirksam) ausweisen |

### 4.2 Unterstützte Standards

IFRS (in der EU übernommene Fassung) und US-GAAP werden vollständig normalisiert. Lokale Standards (HGB, J-GAAP, Ind AS, Swiss GAAP FER, chinesische ASBE und andere) werden mit den verfügbaren Daten bewertet, ohne Normalisierung der Punkte aus 4.3, und erhalten höchstens Konfidenz K3. Der Standard steht an jedem Wert (HR-12).

### 4.3 Normalisierungsregeln

Jede Regel ist ein Eintrag in `config/accounting_adjustments.yaml` mit ID, Version und Quelle. Jede angewandte Anpassung erscheint mit Betrag im Berichtsabschnitt 8 der Analyse (Abschnitt 12.3).

| ID | Thema | IFRS | US-GAAP | Regel im System |
|---|---|---|---|---|
| ACC-01 | Leasing | IFRS 16, fast alle Leasingverhältnisse in der Bilanz, Aufwand als Abschreibung und Zins, EBITDA dadurch höher | ASC 842, Operating Leases in der Bilanz, Aufwand linear im operativen Ergebnis | Basis "nach Leasing" ist Standard. Leasingverbindlichkeiten zählen immer zur Nettoverschuldung. Für US-GAAP-Operating-Leases wird der Leasingaufwand aus dem Anhang zum EBITDA addiert, damit Zähler und Nenner von EV/EBITDA konsistent sind. Zusätzlich wird eine Basis "vor Leasing" gespeichert |
| ACC-02 | Entwicklungskosten | IAS 38, Aktivierung bei erfüllten Kriterien | ASC 730, sofort Aufwand (Ausnahme Software) | Vergleichsbasis "voll aufwandswirksam". Aktivierte Entwicklungskosten der Periode werden als Aufwand gebucht, die Abschreibung darauf zurückgerechnet. Beide EBIT-Varianten werden gespeichert |
| ACC-03 | Vorräte | LIFO verboten | LIFO erlaubt | LIFO-Reserve aus dem Anhang zu den Vorräten addieren, Veränderung der Reserve im Materialaufwand korrigieren |
| ACC-04 | Zinsen und Dividenden in der Kapitalflussrechnung | Bis Geschäftsjahr 2026 Wahlrecht. Ab IFRS 18 (Geschäftsjahre ab 1.1.2027) gezahlte Zinsen und Dividenden unter Finanzierung, erhaltene grundsätzlich unter Investition | Gezahlte Zinsen im operativen Cashflow | Einheitliche FCF-Definition. Gezahlte Zinsen werden immer vom operativen Cashflow abgezogen, wenn sie unter Finanzierung ausgewiesen sind. Die FCFF-Variante addiert Zinsen nach Steuern zurück |
| ACC-05 | Ergebnis-Zwischensummen | Ab IFRS 18 Pflichtsumme "operatives Ergebnis" nach eigener Abgrenzung | Keine einheitliche EBIT-Definition | Das System berechnet EBIT selbst aus Komponenten nach Registerformel und übernimmt keine ausgewiesene Zwischensumme ungeprüft |
| ACC-06 | Bereinigte Kennzahlen des Managements | Ab IFRS 18 Anhangangabe mit Überleitung für managementdefinierte Kennzahlen | SEC Regulation G verlangt Überleitung | Bereinigte Werte sind nie Primärwert. Ein dauerhafter Abstand über 20 Prozent zwischen bereinigt und unbereinigt ist Ungereimtheit INC-05 |
| ACC-07 | Wertaufholung | erlaubt außer bei Goodwill | verboten | Wertaufholungen als Sondereffekt, nicht im normalisierten EBIT |
| ACC-08 | Neubewertung | IAS 16 Neubewertungsmodell, IAS 40 Fair Value mit Erfolgswirkung | Anschaffungskosten | Fair-Value-Änderungen aus dem operativen Ergebnis entfernen |
| ACC-09 | Goodwill | keine planmäßige Abschreibung | keine planmäßige Abschreibung bei Börsennotierten | Bei HGB planmäßige Abschreibung für den Vergleich zurückrechnen. Goodwill-Anteil am Eigenkapital ausweisen |
| ACC-10 | Pensionen | IAS 19, Neubewertungen im OCI, Nettozins im Finanzergebnis | ASC 715, Teile können im operativen Ergebnis stehen | Dienstzeitaufwand operativ, Zinsanteil Finanzierung, Defizit als schuldenähnlicher Posten (`net_debt_incl_pensions`) |
| ACC-11 | Aktienbasierte Vergütung | IFRS 2 | ASC 718 | Immer Aufwand, auch wenn das Management sie herausrechnet |
| ACC-12 | Versicherungsverträge | IFRS 17 seit 2023 | LDTI seit 2023 | Nur innerhalb desselben Standards vergleichen. Zeitreihen vor und nach der Umstellung trennen |
| ACC-13 | Geschäftsjahr | beliebiger Stichtag | beliebiger Stichtag | Für Vergleichsgruppen Kalendarisierung auf einen gemeinsamen Stichtag aus Quartalswerten (TTM). Bei Halbjahresberichtern zeitanteilig mit Konfidenzabschlag |
| ACC-14 | Minderheitsanteile | Ausweis im Eigenkapital | Ausweis im Eigenkapital | Minderheiten zählen zum Unternehmenswert. Kennzahlen je Aktie nur mit dem Ergebnis der Aktionäre des Mutterunternehmens |

### 4.4 Umstellungen und Zeitreihenbrüche

Bei Standardwechseln (IFRS 16 ab 2019, IFRS 17 ab 2023, IFRS 18 ab 2027) markiert das System den Bruch in der Zeitreihe. Trends werden nur über vergleichbare Perioden gerechnet. Liefert der neue Bericht angepasste Vorjahreszahlen, werden diese als eigene Fassung gespeichert (siehe Restatements in 3.2).

### 4.5 Landesumfeld

Das Land der Notierung und des Sitzes wird mit der Einordnung nach Leuz, Nanda und Wysocki als Information im Bericht angezeigt. Es fließt nicht in die Note ein, weil die Einordnung auf älteren Daten beruht. Beneish-Score und Accruals (3.5) messen die Bilanzqualität des einzelnen Unternehmens direkt.
