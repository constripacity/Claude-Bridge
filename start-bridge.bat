@echo off
echo Starting Claude Bridge MCP Server...
cd /d "%~dp0"
python -m claude_bridge %*
pause
