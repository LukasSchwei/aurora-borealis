@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
if defined PYTHONPATH (
    set "PYTHONPATH=%SCRIPT_DIR%;%PYTHONPATH%"
) else (
    set "PYTHONPATH=%SCRIPT_DIR%"
)

if exist "%SCRIPT_DIR%\.venv\Scripts\pythonw.exe" (
    if "%~1"=="" (
        start "" "%SCRIPT_DIR%\.venv\Scripts\pythonw.exe" -m aurora_borealis.main
        exit /b 0
    ) else (
        "%SCRIPT_DIR%\.venv\Scripts\python.exe" -m aurora_borealis.main %*
        exit /b %ERRORLEVEL%
    )
)

if exist "%SCRIPT_DIR%\.venv\Scripts\python.exe" (
    "%SCRIPT_DIR%\.venv\Scripts\python.exe" -m aurora_borealis.main %*
    exit /b %ERRORLEVEL%
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
    if "%~1"=="" (
        start "" pyw -3 -m aurora_borealis.main
        exit /b 0
    ) else (
        py -3 -m aurora_borealis.main %*
        exit /b %ERRORLEVEL%
    )
)

where pythonw >nul 2>&1
if %ERRORLEVEL%==0 if "%~1"=="" (
    start "" pythonw -m aurora_borealis.main
    exit /b 0
)

python -m aurora_borealis.main %*
exit /b %ERRORLEVEL%
