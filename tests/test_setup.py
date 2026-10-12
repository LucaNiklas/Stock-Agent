"""Gerüst: CLI, Formelregister, Agent-Erzeugung und Hooks (Schritt 0)."""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from stockagent.agents.render import RenderError, render_all, render_one, resolve_model
from stockagent.cli import app
from stockagent.core import registry

ROOT = Path(__file__).resolve().parent.parent
MODELS = yaml.safe_load((ROOT / "config" / "models.yaml").read_text(encoding="utf-8"))


def test_cli_version() -> None:
    res = CliRunner().invoke(app, ["version"])
    assert res.exit_code == 0 and res.stdout.strip() == "0.1.0"


def test_cli_unbuilt_commands_say_so() -> None:
    res = CliRunner().invoke(app, ["screen"])
    assert res.exit_code == 2 and "Bauschritt 5" in res.stdout


def test_registry_matches_metrics_yaml() -> None:
    """HR-06: jede Kennzahl in metrics.yaml hat genau eine registrierte Funktion und umgekehrt."""
    cfg = yaml.safe_load((ROOT / "config" / "metrics.yaml").read_text(encoding="utf-8"))
    assert {m["id"] for m in cfg["metrics"]} == registry.ids()


def test_registry_rejects_duplicates() -> None:
    @registry.metric("_test_only")
    def f() -> int:
        return 1

    with pytest.raises(ValueError):
        registry.metric("_test_only")(f)
    registry._REGISTRY.pop("_test_only")


# ---------------------------------------------------------------- Agent-Erzeugung (SPEC 16.4)

TEMPLATE = """---
name: j1-number-checker
description: Prüft Zahlen blind.
model: {{ model.fast }}
---
{{ preamble }}

Du bist Prüfer.
"""


def test_models_yaml_maps_classes() -> None:
    assert resolve_model("fast", MODELS) == "haiku"
    assert resolve_model("standard", MODELS) == "sonnet"
    assert resolve_model("strong", MODELS) == "opus"
    assert resolve_model("extern", MODELS) == "sonnet"  # Gemini aus, Rückfall standard


def test_render_inserts_model_and_preamble() -> None:
    text = render_one(TEMPLATE, "j1.md", "PRÄAMBEL", MODELS)
    assert "model: haiku" in text and "PRÄAMBEL" in text and "{{" not in text


def test_render_requires_preamble() -> None:
    with pytest.raises(RenderError, match="Präambel"):
        render_one(TEMPLATE.replace("{{ preamble }}", ""), "j1.md", "P", MODELS)


def test_render_requires_frontmatter_fields() -> None:
    with pytest.raises(RenderError, match="description"):
        render_one(TEMPLATE.replace("description: Prüft Zahlen blind.\n", ""), "x.md", "P", MODELS)


def test_render_all(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "_preamble.md").write_text("Regeln", encoding="utf-8")
    (src / "j1.md").write_text(TEMPLATE, encoding="utf-8")
    written = render_all(src, tmp_path / "out", ROOT / "config" / "models.yaml")
    assert [p.name for p in written] == ["j1.md"]


def test_preamble_has_all_rules() -> None:
    text = (ROOT / "agents_src" / "_preamble.md").read_text(encoding="utf-8")
    for n in range(1, 11):
        assert f"\n{n}. " in "\n" + text, f"Regel {n} fehlt"


# ---------------------------------------------------------------- Hooks (SPEC 16.5)


def _hook(name: str, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ROOT / "scripts" / "hooks" / name)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT)},
        check=False,
    )


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("/repo/data/raw/abc.json", 2),
        ("/repo/eval/gold/case1.yaml", 2),
        ("/repo/src/stockagent/cli.py", 0),
    ],
)
def test_protect_raw_hook(path: str, code: int) -> None:
    assert _hook("protect_raw.sh", {"tool_input": {"file_path": path}}).returncode == code


def test_stop_hook_does_not_loop() -> None:
    assert _hook("stop_tests.sh", {"stop_hook_active": True}).returncode == 0


def test_cli_render_agents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "models.yaml").write_text(
        (ROOT / "config" / "models.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "agents_src").mkdir()
    (tmp_path / "agents_src" / "_preamble.md").write_text("Regeln", encoding="utf-8")
    (tmp_path / "agents_src" / "j1.md").write_text(TEMPLATE, encoding="utf-8")
    monkeypatch.setenv("STOCKAGENT_HOME", str(tmp_path))
    res = CliRunner().invoke(app, ["render-agents"])
    assert res.exit_code == 0 and "1 Agent-Dateien" in res.stdout
    assert "model: haiku" in (tmp_path / ".claude" / "agents" / "j1.md").read_text()


def test_cli_serve_without_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKAGENT_HOME", str(tmp_path))
    res = CliRunner().invoke(app, ["universe", "serve", "--no-open"])
    assert res.exit_code == 1 and "stockagent universe update" in res.stdout
