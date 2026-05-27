#!/bin/bash
# Start Claude Bridge on macOS
# Run once before any bridged Claude Code session

cd "$(dirname "$0")"
echo "Starting Claude Bridge..."
python3 server.py
