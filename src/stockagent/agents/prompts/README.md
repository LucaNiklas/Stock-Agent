# src/stockagent/agents/prompts/

Die Prompts der Agenten stehen als Vorlagen in `agents_src/` (Frontmatter mit Werkzeugrechten,
Modellklasse und Hooks, darunter der Systemprompt). `uv run stockagent render-agents` erzeugt
daraus `.claude/agents/*.md` und die JSON-Schemas unter `schemas/json/`.

`versions.yaml` hält die Version je Vorlage. Sie steht mit dem Hash der gerenderten Datei im
Umschlag jeder Agentenausgabe (SPEC 8.4). Jede Änderung braucht einen Eval-Lauf (CLAUDE.md,
SPEC 11.6).
