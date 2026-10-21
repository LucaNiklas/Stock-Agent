#!/bin/bash
# Stop-Hook der Subagents der Tiefenanalyse (in Subagents als SubagentStop, SPEC 15.1 Nr. 3).
# Gibt die letzte Antwort an `stockagent accept --hook`. Exit-Code 2 schickt die Fehlermeldung
# an den Agenten zurück, damit er die Antwort berichtigt (höchstens zweimal, dann eskaliert).
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
exec uv run --quiet stockagent accept --hook
