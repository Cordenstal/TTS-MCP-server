@echo off
setlocal EnableExtensions
title TTS MCP Server - Elevated Quick Restart

net session >nul 2>&1
if not errorlevel 1 goto elevated

echo Requesting Administrator permission so screen capture can access an elevated TTS window...
powershell.exe -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%ComSpec%' -ArgumentList '/c ""%~f0"" elevated'"
exit /b

:elevated
call "%~dp0quick_restart.bat"
endlocal
