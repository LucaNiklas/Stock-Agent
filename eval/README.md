# eval/

Goldstandard der Prüfer (SPEC 11.6, ADR 0013).

- `gold/`: von Luca geprüfte Fälle (`luca_geprueft: true`). Für Agenten schreibgeschützt.
- `kandidaten/`: Fälle aus SEC-Daten (Company Facts und 10-K), noch nicht von Luca geprüft. Nach
  der Prüfung nach `gold/` verschieben.
- `aufzeichnungen/`: Urteile von J2 aus Live-Läufen mit Version der Vorlage und Modell. Die CI
  wertet die letzte aus und verlangt einen neuen Lauf, wenn sich die Vorlage geändert hat.
- `laeufe/`: Eingaben und Rohantworten je Live-Lauf (nicht versioniert).

Befehle:

    uv run python eval/run_eval.py                    deterministisch, wie in der CI
    uv run python eval/run_eval.py --live             J1 gegen die eigene Datenbank, J2 über claude -p
    uv run python eval/run_eval.py --live --gemini    J2 über Gemini, sonst Rückfall auf Claude
    uv run stockagent tool gemini-test                antwortet die Gemini CLI?

Für J1 live müssen die fünf Unternehmen geladen sein:
`uv run stockagent bewerten <ISIN>` für US0378331005, US46625H1005, US7433151039, US7561091049,
US4581401001.

Fehlerarten: J1 `falsche_zahl`, `falsche_periode` (zählen zur Quote, Mindestwert 95 %),
`falsche_periode_unter_toleranz` (Grenzfall, J1 soll mindestens warnen). J2
`erfundene_aussage`, `eingebettete_anweisung` (Mindestwert 85 %). `keiner` misst Fehlalarme.
