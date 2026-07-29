@echo off
setlocal EnableExtensions
title TTS MCP Server - Quick Restart

cd /d "%~dp0..\.."
echo ========================================
echo TTS MCP Server - Quick Restart
echo ========================================
echo.

call "%~dp0quick_start.bat"
endlocal
