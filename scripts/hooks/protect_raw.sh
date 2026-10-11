#!/usr/bin/env bash
# PreToolUse-Hook auf Edit|Write: Rohdaten und Goldstandard sind unveränderlich (SPEC 7.6, 16.5).
path=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("file_path",""))')
case "$path" in
  */data/raw/*|*/eval/gold/*)
    echo "Gesperrt: $path ist unveränderlich (Rohdaten oder Goldstandard)." >&2
    exit 2 ;;
esac
exit 0
