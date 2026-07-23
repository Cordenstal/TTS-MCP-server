@echo off
setlocal EnableExtensions
title TTS MCP Server - Quick Restart

cd /d "%~dp0"
echo ========================================
echo TTS MCP Server - Quick Restart
echo ========================================
echo.

echo Stopping the existing AI gateway/server on port 8765...
for /f "tokens=5" %%P in ('netstat -aon ^| findstr ":8765" ^| findstr "LISTENING"') do (
    echo Stopping process %%P
    taskkill /F /T /PID %%P >nul 2>&1
)

echo Stopping the optional supervisor on port 8770...
for /f "tokens=5" %%P in ('netstat -aon ^| findstr ":8770" ^| findstr "LISTENING"') do (
    echo Stopping process %%P
    taskkill /F /T /PID %%P >nul 2>&1
)

timeout /t 2 /nobreak >nul
call "%~dp0quick_start.bat"
endlocal
