@echo off
echo Starting Claude Bridge TUI...
cd /d "%~dp0"
python -m claude_bridge.tui %*
