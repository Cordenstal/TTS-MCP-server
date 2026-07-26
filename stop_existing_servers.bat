@echo off
setlocal EnableExtensions

cd /d "%~dp0"
echo Stopping existing TTS MCP server instances...

rem These ports are reserved by this project. Stop listeners before starting
rem a fresh gateway so stale Python processes cannot receive TTS chat.
for %%P in (8765 8770) do (
    for /f "tokens=5" %%Q in ('netstat -aon ^| findstr ":%%P" ^| findstr "LISTENING"') do (
        echo Stopping process %%Q on port %%P
        taskkill /F /T /PID %%Q >nul 2>&1
    )
)

rem Also stop project server processes that are no longer listening, while
rem leaving unrelated Python programs alone.
set "TTS_MCP_ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$root=[IO.Path]::GetFullPath($env:TTS_MCP_ROOT).TrimEnd('\'); $targets=Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -match '(?i)(server|bridge_supervisor)\.py' -and $_.CommandLine -like ('*' + $root + '*') }; foreach ($target in $targets) { Write-Host ('Stopping TTS MCP process ' + $target.ProcessId); Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue }"

endlocal
exit /b 0
