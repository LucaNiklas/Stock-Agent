#!/bin/bash
# Doppelklick startet das Dashboard (macOS). Beenden: Fenster schließen oder Strg+C.
cd "$(dirname "$0")" && uv run stockagent app
