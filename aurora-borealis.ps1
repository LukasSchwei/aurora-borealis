$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$ScriptDir;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $ScriptDir
}

$VenvPy = Join-Path $ScriptDir ".venv\Scripts\python.exe"
if (Test-Path $VenvPy) {
    & $VenvPy -m aurora_borealis.main @args
    exit $LASTEXITCODE
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -m aurora_borealis.main @args
    exit $LASTEXITCODE
}

& python -m aurora_borealis.main @args
exit $LASTEXITCODE
