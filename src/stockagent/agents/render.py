"""Erzeugt `.claude/agents/*.md` aus den Vorlagen in `agents_src/` (SPEC 16.4).

Ersetzt `{{ preamble }}` durch die Pflicht-Präambel (17.6) und `{{ model.<klasse> }}` durch das
Modell aus `config/models.yaml`. Bricht ab, wenn die Präambel fehlt oder Pflichtfelder fehlen.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

PREAMBLE_TAG = "{{ preamble }}"
MODEL_TAG = re.compile(r"\{\{ model\.([a-z]+) \}\}")
TURNS_TAG = "{{ max_turns }}"
PREAMBLE_FILE = "_preamble.md"


class RenderError(ValueError):
    pass


def resolve_model(model_class: str, models_cfg: dict[str, Any]) -> str:
    classes: dict[str, str] = models_cfg["klassen"]
    if model_class not in classes:
        raise RenderError(f"unbekannte Modellklasse: {model_class}")
    if model_class == "extern":
        extern = models_cfg.get("extern", {})
        if not extern.get("aktiv", False):
            return resolve_model(extern.get("rueckfall", "standard"), models_cfg)
        raise RenderError("externe Modelle werden in Bauschritt 10 angebunden")
    return classes[model_class]


def _frontmatter(text: str, name: str) -> dict[str, Any]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise RenderError(f"{name}: Frontmatter fehlt")
    data = yaml.safe_load(m.group(1)) or {}
    for key in ("name", "description"):
        if not data.get(key):
            raise RenderError(f"{name}: Pflichtfeld '{key}' fehlt")
    return dict(data)


def render_one(template: str, name: str, preamble: str, models_cfg: dict[str, Any]) -> str:
    if PREAMBLE_TAG not in template:
        raise RenderError(f"{name}: Pflicht-Präambel {PREAMBLE_TAG} fehlt (SPEC 17.6)")
    text = MODEL_TAG.sub(lambda m: resolve_model(m.group(1), models_cfg), template)
    if TURNS_TAG in text:
        turns = models_cfg.get("aufwand", {}).get("max_turns", {}).get(name.removesuffix(".md"))
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
    written = []
    for src in sorted(src_dir.glob("*.md")):
        if src.name == PREAMBLE_FILE:
            continue
        target = out_dir / src.name
        target.write_text(
            render_one(src.read_text(encoding="utf-8"), src.name, preamble, models_cfg),
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
