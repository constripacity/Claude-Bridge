@echo off
REM Prefer the Python Launcher (`py`) so a fresh Windows install without
REM Python on PATH doesn't trigger the Microsoft Store stub. Falls back to
REM whatever `python` resolves to if the launcher isn't installed.
echo Starting Claude Bridge MCP Server...
cd /d "%~dp0"
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -m claude_bridge %*
) else (
    python -m claude_bridge %*
)
pause
