@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0setup-wizard-windows.ps1" %*
exit /b %ERRORLEVEL%
