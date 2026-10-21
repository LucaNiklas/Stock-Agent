"""Erzeugt `.claude/agents/*.md` aus den Vorlagen in `agents_src/` (SPEC 16.4).

Ersetzt `{{ preamble }}` durch die Pflicht-Präambel (17.6) und `{{ model.<klasse> }}` durch das
Modell aus `config/models.yaml`. Bricht ab, wenn die Präambel fehlt oder Pflichtfelder fehlen.

Varianten (Bauschritt 10, Jury J3): Ein Eintrag unter `tiefenanalyse.agenten` mit `quelle` macht
aus der Vorlage `quelle` eine eigene Agent-Datei `vorlage`. `{{ name }}` wird zum Dateinamen,
`{{ model.richter }}` zum Modell dieses Platzes (`richter`) aus der Liste unter `modell_von`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

PREAMBLE_TAG = "{{ preamble }}"
MODEL_TAG = re.compile(r"\{\{ model\.([a-z]+) \}\}")
TURNS_TAG = "{{ max_turns }}"
NAME_TAG = "{{ name }}"
RICHTER_TAG = "{{ model.richter }}"
PREAMBLE_FILE = "_preamble.md"


class RenderError(ValueError):
    pass


def resolve_model(
    model_class: str, models_cfg: dict[str, Any], rueckfall: str | None = None
) -> str:
    """Modell einer Klasse. `extern` ohne aktiven Zugang wird zu `rueckfall` (sonst dem
    allgemeinen Rückfall aus `extern.rueckfall`)."""
    classes: dict[str, str] = models_cfg["klassen"]
    if model_class not in classes:
        raise RenderError(f"unbekannte Modellklasse: {model_class}")
    if model_class == "extern":
        extern = models_cfg.get("extern", {})
        if not extern.get("aktiv", False):
            return resolve_model(rueckfall or extern.get("rueckfall", "standard"), models_cfg)
        raise RenderError("Gemini als Subagent ist nicht angebunden (ADR 0013)")
    return classes[model_class]


def agent_klasse(agent_cfg: dict[str, Any], models_cfg: dict[str, Any]) -> tuple[str, str | None]:
    """Modellklasse eines Agenten der Tiefenanalyse und sein Rückfall für `extern`."""
    von = agent_cfg["modell_von"]
    wert = models_cfg["agenten"][von]
    if "richter" in agent_cfg:
        wert = dict(enumerate(wert, start=1))[int(agent_cfg["richter"])]
    rueckfall = models_cfg["agenten"].get(f"{von}_rueckfall_extern") if wert == "extern" else None
    return str(wert), rueckfall


def _frontmatter(text: str, name: str) -> dict[str, Any]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise RenderError(f"{name}: Frontmatter fehlt")
    data = yaml.safe_load(m.group(1)) or {}
    for key in ("name", "description"):
        if not data.get(key):
            raise RenderError(f"{name}: Pflichtfeld '{key}' fehlt")
    return dict(data)


def render_one(
    template: str,
    name: str,
    preamble: str,
    models_cfg: dict[str, Any],
    *,
    vorlage: str | None = None,
    richter_modell: str | None = None,
) -> str:
    """`name`: Dateiname der Agent-Datei, `vorlage`: Dateiname der Vorlage, wenn verschieden
    (Varianten), für die Grenze `max_turns`."""
    if PREAMBLE_TAG not in template:
        raise RenderError(f"{name}: Pflicht-Präambel {PREAMBLE_TAG} fehlt (SPEC 17.6)")
    if RICHTER_TAG in template:
        if richter_modell is None:
            raise RenderError(f"{name}: Vorlage für Varianten, nur über tiefenanalyse.agenten")
        template = template.replace(RICHTER_TAG, richter_modell)
    text = MODEL_TAG.sub(lambda m: resolve_model(m.group(1), models_cfg), template)
    text = text.replace(NAME_TAG, name.removesuffix(".md"))
    if TURNS_TAG in text:
        schluessel = (vorlage or name).removesuffix(".md")
        turns = models_cfg.get("aufwand", {}).get("max_turns", {}).get(schluessel)
        if turns is None:
            raise RenderError(f"{name}: aufwand.max_turns fehlt in config/models.yaml")
        text = text.replace(TURNS_TAG, str(int(turns)))
    text = text.replace(PREAMBLE_TAG, preamble.strip())
    _frontmatter(text, name)
    return text


def render_all(src_dir: Path, out_dir: Path, models_file: Path) -> list[Path]:
    models_cfg = yaml.safe_load(models_file.read_text(encoding="utf-8"))
    preamble = (src_dir / PREAMBLE_FILE).read_text(encoding="utf-8")
    out_dir.mkdir(parents=True, exist_ok=True)
    varianten = [
        a for a in models_cfg.get("tiefenanalyse", {}).get("agenten", {}).values() if "quelle" in a
    ]
    quellen = {a["quelle"] for a in varianten}
    written = []
    for src in sorted(src_dir.glob("*.md")):
        if src.name == PREAMBLE_FILE or src.stem in quellen:
            continue
        target = out_dir / src.name
        target.write_text(
            render_one(src.read_text(encoding="utf-8"), src.name, preamble, models_cfg),
            encoding="utf-8",
        )
        written.append(target)
    for a in varianten:
        src = src_dir / f"{a['quelle']}.md"
        if not src.exists():
            continue
        klasse, rueckfall = agent_klasse(a, models_cfg)
        target = out_dir / f"{a['vorlage']}.md"
        target.write_text(
            render_one(
                src.read_text(encoding="utf-8"),
                target.name,
                preamble,
                models_cfg,
                vorlage=src.name,
                richter_modell=resolve_model(klasse, models_cfg, rueckfall),
            ),
            encoding="utf-8",
        )
        written.append(target)
    return written


def export_schemas(out_dir: Path) -> list[Path]:
    """JSON-Schemas der Agentenantworten nach schemas/json/ (SPEC 8.4)."""
    import json

    from stockagent.schemas.agents import ANTWORTEN

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for modell in dict.fromkeys(ANTWORTEN.values()):
        ziel = out_dir / f"{modell.__name__}.json"
        ziel.write_text(
            json.dumps(modell.model_json_schema(), ensure_ascii=False, indent=2) + "\n", "utf-8"
        )
        written.append(ziel)
    return written
