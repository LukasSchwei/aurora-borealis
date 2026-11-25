$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $RepoRoot

$VenvDir = Join-Path $RepoRoot ".venv-build"
python -m venv $VenvDir
$Py = Join-Path $VenvDir "Scripts\python.exe"

& $Py -m pip install --upgrade pip setuptools wheel
& $Py -m pip install -r requirements.txt pyinstaller

$SvgPath = Join-Path $RepoRoot "aurora_borealis\assets\aurora-borealis.svg"
$IcoPath = Join-Path $RepoRoot "aurora_borealis\assets\aurora-borealis.ico"
$IconGenScript = @'
import struct, sys
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication, QIcon
app = QGuiApplication.instance() or QGuiApplication([])
pix = QIcon(sys.argv[1]).pixmap(256, 256)
buf = QBuffer()
buf.open(QIODevice.OpenModeFlag.WriteOnly)
pix.save(buf, "PNG")
png = bytes(buf.data())
with open(sys.argv[2], "wb") as f:
    f.write(struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22) + png)
'@
& $Py -c $IconGenScript $SvgPath $IcoPath

& $Py -m PyInstaller --noconfirm --clean --windowed `
    --name "AuroraBorealis" `
    --icon $IcoPath `
    --add-data "aurora_borealis\assets;aurora_borealis\assets" `
    aurora_borealis\main.py

$Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (Test-Path $Iscc) {
    & $Iscc (Join-Path $PSScriptRoot "aurora-borealis.iss")
    Write-Host "Built Inno Setup installer in dist\AuroraBorealis-Setup-0.2.0.exe" -ForegroundColor Green
} else {
    Write-Host "PyInstaller bundle ready in dist\AuroraBorealis\. Install Inno Setup 6 and run ISCC on packaging\windows\aurora-borealis.iss to produce Setup.exe." -ForegroundColor Yellow
}
