"""Agent-Dateien aus agents_src/ erzeugen: uv run python scripts/render_agents.py"""

from pathlib import Path

from stockagent.agents.render import render_all

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    written = render_all(
        ROOT / "agents_src", ROOT / ".claude" / "agents", ROOT / "config" / "models.yaml"
    )
    print(f"{len(written)} Agent-Dateien erzeugt")
