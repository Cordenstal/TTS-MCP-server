@echo off
setlocal EnableExtensions
title TTS MCP Server - Quick Start

set "ROOT_DIR=%~dp0..\.."
cd /d "%ROOT_DIR%"
call "%~dp0stop_existing_servers.bat"
set "PYTHON=python"
if exist "%ROOT_DIR%\.venv\Scripts\python.exe" (
    set "PYTHON=%ROOT_DIR%\.venv\Scripts\python.exe"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Python was not found in PATH and no project virtual environment exists.
        pause
        exit /b 1
    )
)

echo ========================================
echo TTS MCP Server - Quick Start
echo HTTP AI gateway: 127.0.0.1:8765
echo ========================================
echo.

"%PYTHON%" --version
if errorlevel 1 (
    echo ERROR: Python could not be started.
    pause
    exit /b 1
)

"%PYTHON%" -c "import mcp" >nul 2>&1
if errorlevel 1 (
    echo ERROR: MCP dependencies are not installed in the selected Python environment.
    echo Install the project dependencies before starting the server.
    pause
    exit /b 1
)

echo Starting gateway-only server in this window...
set "TTS_GATEWAY_ONLY=1"
set "AI_CHAT_HISTORY_TURNS=12"
if not defined TTS_TRACE set "TTS_TRACE=1"
if not defined PYTHONUNBUFFERED set "PYTHONUNBUFFERED=1"
if not exist "tts_mcp_backend.json" (
    echo Configuring direct Ollama backend...
    set "AI_BACKEND_KIND=http"
    set "AI_BACKEND_URL=http://127.0.0.1:11434/api/chat"
    set "AI_BACKEND_MODEL=gemma4:12b"
    set "AI_BACKEND_FORMAT=ollama"
    set "AI_BACKEND_TIMEOUT=300"
)
echo Open the AI control panel at http://127.0.0.1:8765/admin
echo Runtime traces are written under .tmp\.
echo This console will show live AI and TTS trace events.
echo.
"%PYTHON%" -m tts_mcp.app.server
set "SERVER_EXIT=%ERRORLEVEL%"
echo.
echo TTS MCP Server stopped with exit code %SERVER_EXIT%.
pause
endlocal & exit /b %SERVER_EXIT%
