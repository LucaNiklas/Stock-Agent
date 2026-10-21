"""Goldstandard-Lauf (SPEC 11.6). Logik in `stockagent.goldstandard`.

    uv run python eval/run_eval.py              deterministisch (auch in der CI)
    uv run python eval/run_eval.py --live       J1 gegen die eigene Datenbank, J2 über claude -p,
                                                Aufzeichnung nach eval/aufzeichnungen/
    uv run python eval/run_eval.py --live --gemini   J2 über Gemini (ADR 0013), sonst Rückfall

Fangquote je Fehlerart, Fehlalarme, Kappa der Jury gegen Lucas Entscheidungen. Exit-Code 1, wenn
ein Fall in sich nicht stimmt oder eine Quote unter dem Mindestwert aus config/models.yaml liegt.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal

from stockagent import goldstandard
from stockagent.paths import Paths


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--live", action="store_true", help="J1 und J2 wirklich laufen lassen")
    p.add_argument("--json", action="store_true", help="Bericht als JSON")
    p.add_argument("--gemini", action="store_true", help="J2 über Gemini statt Claude (mit --live)")
    args = p.parse_args()
    paths = Paths.default()
    now = datetime.now(UTC)
    berichte = []
    for satz in goldstandard.laden(paths.root):
        if not satz.j1 and not satz.j2:
            continue
        if args.live:
            from stockagent.agents.tools import nachrechnen

            j1: dict[str, Decimal | None] = {}
            for f in satz.j1:
                erg = nachrechnen.nachrechnen(paths, f.isin, [f.ref])[0]
                j1[f.id] = Decimal(erg["wert"]) if erg.get("status") == "berechnet" else None
            modell = "claude (Modell der Agent-Datei j2-belegpruefer)"
            j2: dict[str, str | None] = {}
            if satz.j2 and args.gemini:
                from stockagent.agents.tools import gemini

                try:
                    j2 = goldstandard.j2_gemini(paths, satz.j2, now=now, pruefe_verfuegbar=False)
                    modell = "gemini"
                except gemini.GeminiNichtVerfuegbar as exc:
                    print(f"Gemini nicht verfügbar ({exc}), Rückfall auf Claude")
            if satz.j2 and not j2:
                j2 = goldstandard.j2_live(paths, satz.j2, now=now)
            goldstandard.aufzeichnen(paths, j2, modell, now)
            b = goldstandard.auswerten(paths, satz, modus="live", j1_werte=j1, j2_urteile=j2)
        else:
            b = goldstandard.auswerten(paths, satz)
        berichte.append(b)

    if args.json:
        print(
            json.dumps(
                [goldstandard.als_dict(b) for b in berichte],
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
    else:
        for b in berichte:
            stand = "bestanden" if b.bestanden else "NICHT bestanden"
            print(f"== {b.herkunft} ({b.modus}): {stand}")
            for f in b.stimmigkeit:
                print(f"  Fall fehlerhaft: {f}")
            for name, q in b.quoten.items():
                print(f"  {name}: {q}")
            for h in b.hinweise:
                print(f"  Hinweis: {h}")
            for e in b.ergebnisse:
                if e.erkannt is False:
                    print(f"  nicht erkannt: {e.fall} ({e.fehlerart}) Urteil {e.urteil}")
        k = goldstandard.kappa_jury(paths)
        print(f"Jury gegen Luca: {k}")
    return 0 if all(b.bestanden for b in berichte) else 1


if __name__ == "__main__":
    sys.exit(main())
