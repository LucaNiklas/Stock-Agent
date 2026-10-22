"""Dashboard als statische Datei für den Lesemodus (SPEC 13.3, 13.5).

Schreibt eine einzelne HTML-Datei mit eingebetteten Daten: Liste aller Aktien, Unternehmensseite
der bewerteten Titel, Änderungen, Karte, Historie und Methodik. Sie braucht keinen Server und
lässt sich als Datei öffnen oder als privates Artifact teilen. Filtern und Suche nach Namen gehen
im Browser, Bewerten, Freitext und Speichern nur im lokalen Dashboard (`stockagent app`).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from stockagent import historie
from stockagent.paths import Paths
from stockagent.titelliste import FILTER, Daten, karte


def daten_fuer_lesemodus(paths: Paths) -> dict[str, Any]:
    from stockagent.dashboard import app

    daten = Daten(paths)
    bewertet = [z.isin for z in daten.zeilen if z.note]
    titel = {isin: app.titel_detail(paths, isin) for isin in bewertet}
    return {
        "erstellt": datetime.now(UTC).strftime("%d.%m.%Y %H:%M UTC"),
        "stand": daten.stand,
        "filter": list(FILTER),
        "horizonte": daten.horizont_info,
        "horizont_standard": daten.horizont_standard,
        "zeilen": [asdict(z) for z in daten.zeilen],
        "titel": titel,
        "vergleich": {i: app.vergleich(paths, [i])[0] for i in bewertet},
        "fest": {
            "/api/aenderungen": historie.aenderungen(paths),
            "/api/historie": app.historie_daten(paths),
            "/api/methodik": historie.methodik(paths),
            "/api/karte": karte(daten, {}),
        },
    }


def bauen(paths: Paths, ziel: Path) -> Path:
    """Statische Datei schreiben. Zurück der Pfad."""
    seite = files("stockagent.dashboard").joinpath("template.html").read_text("utf-8")
    daten = json.dumps(daten_fuer_lesemodus(paths), ensure_ascii=False, default=str)
    # Schließende Script-Marken in Daten (Firmennamen, Texte) unschädlich machen
    daten = daten.replace("</", "<\\/")
    einbettung = f"<script>window.LESEMODUS={daten};</script>\n<script>"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(seite.replace("<script>", einbettung, 1), "utf-8")
    return ziel
