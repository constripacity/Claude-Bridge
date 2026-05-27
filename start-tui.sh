#!/bin/bash
# Start the Claude Bridge terminal UI (companion to the web dashboard).
# Pass --url / --sender to point at a remote bridge or override sender id.

cd "$(dirname "$0")"
python3 -m claude_bridge.tui "$@"
