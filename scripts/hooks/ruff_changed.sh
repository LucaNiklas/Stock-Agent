#!/usr/bin/env bash
# PostToolUse-Hook auf Edit|Write: geänderte Python-Datei unter src/ sofort mit ruff prüfen.
path=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("file_path",""))')
case "$path" in
  */src/*.py|*/tests/*.py)
    cd "$CLAUDE_PROJECT_DIR" && uv run ruff check --fix --quiet "$path" >&2 || exit 2 ;;
  */config/*|*/prompts/*|*/agents_src/*)
    echo "Hinweis: Methodik- oder Prompt-Änderung. Changelog und Eval-Lauf nachziehen (SPEC 16.5)." >&2 ;;
esac
exit 0
