@echo off
setlocal
powershell -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0installer\windows_wizard.ps1" %*
if errorlevel 1 (
    echo.
    echo Aurora Borealis Setup Wizard exited with error code %ERRORLEVEL%.
    echo Re-running with console output so you can inspect any error:
    powershell -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0installer\windows_wizard.ps1" %*
    pause
)
exit /b %ERRORLEVEL%
