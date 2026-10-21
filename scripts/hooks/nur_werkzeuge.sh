#!/bin/bash
# PreToolUse-Hook für Bash in Subagents der Tiefenanalyse (SPEC 16.4): erlaubt nur die
# Lese-Werkzeuge `uv run stockagent tool ...`, ohne Verkettung, Umleitung oder Ersetzung.
# Exit-Code 2 blockiert den Aufruf und gibt die Meldung an den Agenten zurück.
befehl=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))')
if [[ "$befehl" =~ ^uv\ run\ stockagent\ tool\ (rechenweg|nachrechnen)\ [A-Za-z0-9@_\ .-]+$ ]]; then
  exit 0
fi
echo "Nicht erlaubt: nur 'uv run stockagent tool rechenweg|nachrechnen <ISIN> <ref> ...' ohne ; | & \$ > <" >&2
exit 2
