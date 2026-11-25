@echo off
setlocal
echo Launching Aurora Borealis Windows Installer...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-windows.ps1" -CreateDesktopShortcut -RegisterFileAssociations %*
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
    echo.
    echo Installer exited with error code %EC%.
    pause
)
exit /b %EC%
