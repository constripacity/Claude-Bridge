#!/bin/bash
# Start Claude Bridge
# Run once before any bridged Claude Code session.

cd "$(dirname "$0")"
echo "Starting Claude Bridge..."
python3 -m claude_bridge "$@"
