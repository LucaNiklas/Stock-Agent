#!/usr/bin/env bash
# Stop-Hook: keine Arbeitssitzung endet mit roten Tests (SPEC 16.5).
# Läuft der Hook schon einmal (stop_hook_active), nicht erneut blockieren, damit keine Schleife entsteht.
active=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("stop_hook_active", False))')
[ "$active" = "True" ] && exit 0
cd "$CLAUDE_PROJECT_DIR" || exit 0
if ! out=$(uv run pytest -q -x -m "not slow" 2>&1); then
  echo "Tests sind rot, bitte beheben:" >&2
  echo "$out" | tail -30 >&2
  exit 2
fi
exit 0
