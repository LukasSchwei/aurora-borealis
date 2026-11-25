param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "Aurora Borealis\app"),
    [switch]$InPlace,
    [switch]$CreateDesktopShortcut = $true,
    [switch]$NoDesktopShortcut,
    [switch]$RegisterFileAssociations = $true,
    [switch]$NoFileAssociations,
    [switch]$SkipWinget,
    [switch]$InstallAuroraLegacy,
    [switch]$InstallFiveTools
)

$ErrorActionPreference = "Stop"
$InstallerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoDir = Split-Path -Parent $InstallerDir
$DoDesktopShortcut = ([bool]$CreateDesktopShortcut) -and (-not $NoDesktopShortcut.IsPresent)
$DoFileAssociations = ([bool]$RegisterFileAssociations) -and (-not $NoFileAssociations.IsPresent)

function Invoke-NativeChecked {
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Command,
        [string]$Description = "Command"
    )
    $prevPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $global:LASTEXITCODE = 0
        & $Command
        $ec = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevPref
    }
    if ($ec -ne 0) {
        throw "$Description failed with exit code $ec."
    }
}

function Find-Python310 {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            $ver = & py -3 -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>$null
            if ($ver) {
                $parts = $ver.Split('.')
                if ([int]$parts[0] -gt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 10)) {
                    return @("py", "-3")
                }
            }
        } catch {}
    }
    foreach ($cmd in @("python", "python3")) {
        if (Get-Command $cmd -ErrorAction SilentlyContinue) {
            try {
                $ver = & $cmd -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>$null
                if ($ver) {
                    $parts = $ver.Split('.')
                    if ([int]$parts[0] -gt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 10)) {
                        return @($cmd)
                    }
                }
            } catch {}
        }
    }
    $localPy = Join-Path $env:LOCALAPPDATA "Programs\Python"
    if (Test-Path $localPy) {
        $found = Get-ChildItem -Path $localPy -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) {
            return @($found.FullName)
        }
    }
    return $null
}

Write-Host "=== Aurora Borealis Windows Installer ===" -ForegroundColor Cyan

$PythonCmd = Find-Python310
if (-not $PythonCmd) {
    if (-not $SkipWinget -and (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host "[1/5] Installing Python 3.12 via winget..."
        Invoke-NativeChecked { & winget install --id Python.Python.3.12 -e --source winget --scope user --accept-package-agreements --accept-source-agreements } "winget install Python.Python.3.12"
        $env:PATH = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
        $PythonCmd = Find-Python310
    }
    if (-not $PythonCmd) {
        Write-Error "Python 3.10+ is required. Install Python 3 from https://www.python.org/downloads/windows/ and re-run setup-wizard-windows.bat."
    }
}
Write-Host "[1/5] Using Python: $($PythonCmd -join ' ')"

if (-not $SkipWinget -and -not (Get-Command 7z -ErrorAction SilentlyContinue) -and -not (Test-Path "C:\Program Files\7-Zip\7z.exe")) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Optional: installing 7-Zip via winget for Aurora .msi extraction..."
        try {
            Invoke-NativeChecked { & winget install --id 7zip.7zip -e --source winget --accept-package-agreements --accept-source-agreements } "winget install 7zip.7zip"
        } catch {
            Write-Warning "Could not install 7-Zip automatically; Aurora GitHub/5e.tools features still work without it."
        }
    }
}

if ($InPlace) {
    $TargetDir = $RepoDir
    Write-Host "[2/5] Installing in-place at $TargetDir"
} else {
    $TargetDir = $InstallDir
    Write-Host "[2/5] Copying Aurora Borealis files to $TargetDir..."
    New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
    $ItemsToCopy = @(
        "aurora_borealis",
        "installer",
        "aurora-borealis.bat",
        "setup-wizard-windows.bat",
        "pyproject.toml",
        "README.md"
    )
    foreach ($item in $ItemsToCopy) {
        $src = Join-Path $RepoDir $item
        if (Test-Path $src) {
            $dst = Join-Path $TargetDir $item
            if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
            Copy-Item -Recurse -Force $src $dst
        }
    }
    Get-ChildItem -Path $TargetDir -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "[3/5] Creating virtual environment and installing dependencies (PySide6, lxml, pypdf)..."
$VenvDir = Join-Path $TargetDir ".venv"
if ($PythonCmd.Count -eq 2) {
    Invoke-NativeChecked { & $PythonCmd[0] $PythonCmd[1] -m venv $VenvDir } "Create virtual environment"
} else {
    Invoke-NativeChecked { & $PythonCmd[0] -m venv $VenvDir } "Create virtual environment"
}
$VenvPy = Join-Path $VenvDir "Scripts\python.exe"
Invoke-NativeChecked { & $VenvPy -m pip install --upgrade pip setuptools wheel } "Upgrade pip/setuptools/wheel"
Invoke-NativeChecked { & $VenvPy -m pip install --no-build-isolation -e $TargetDir } "Install Aurora Borealis package"

$BundledTplDir = Join-Path $TargetDir "aurora_borealis\assets\templates"
$UserTplDir = Join-Path $env:LOCALAPPDATA "Aurora Borealis\templates"
$SeededTpls = 0
if (Test-Path $BundledTplDir) {
    New-Item -ItemType Directory -Force -Path $UserTplDir | Out-Null
    foreach ($pdf in (Get-ChildItem -Path $BundledTplDir -Filter "*.pdf" -File -ErrorAction SilentlyContinue)) {
        $dstPdf = Join-Path $UserTplDir $pdf.Name
        if (-not (Test-Path $dstPdf)) {
            Copy-Item -Force $pdf.FullName $dstPdf
        }
        $SeededTpls++
    }
}
Write-Host "  PDF Templates: $SeededTpls ready in $UserTplDir"

Write-Host "[4/5] Preparing application icon (.ico) and shortcuts..."
$SvgPath = Join-Path $TargetDir "aurora_borealis\assets\aurora-borealis.svg"
$IcoPath = Join-Path $TargetDir "aurora_borealis\assets\aurora-borealis.ico"
if (-not (Test-Path $IcoPath) -and (Test-Path $SvgPath)) {
    $IconGenScript = @'
import struct, sys
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
app = QGuiApplication.instance() or QGuiApplication([])
renderer = QSvgRenderer(sys.argv[1])
if renderer.isValid():
    blobs = []
    for sz in (16, 24, 32, 48, 64, 128, 256):
        img = QImage(sz, sz, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        renderer.render(p)
        p.end()
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        blobs.append((sz, bytes(buf.data())))
    off = 6 + 16 * len(blobs)
    dirs = []
    for sz, b in blobs:
        wb = 0 if sz >= 256 else sz
        dirs.append(struct.pack("<BBBBHHII", wb, wb, 0, 0, 1, 32, len(b), off))
        off += len(b)
    with open(sys.argv[2], "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(blobs)) + b"".join(dirs) + b"".join(b for _, b in blobs))
'@
    & $VenvPy -c $IconGenScript $SvgPath $IcoPath
}

$WshShell = New-Object -ComObject WScript.Shell
$StartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$LauncherPath = Join-Path $TargetDir "aurora-borealis.bat"

$StartShortcut = $WshShell.CreateShortcut((Join-Path $StartMenuDir "Aurora Borealis.lnk"))
$StartShortcut.TargetPath = $LauncherPath
$StartShortcut.WorkingDirectory = $TargetDir
$StartShortcut.Description = "Aurora Borealis - D&D 5e / 5.5e Character & Companion Builder"
if (Test-Path $IcoPath) { $StartShortcut.IconLocation = "$IcoPath,0" }
$StartShortcut.Save()
Write-Host "Created Start Menu shortcut in $StartMenuDir"

$WizardLauncher = Join-Path $TargetDir "setup-wizard-windows.bat"
if (Test-Path $WizardLauncher) {
    $WizShortcut = $WshShell.CreateShortcut((Join-Path $StartMenuDir "Aurora Borealis Setup Wizard.lnk"))
    $WizShortcut.TargetPath = $WizardLauncher
    $WizShortcut.WorkingDirectory = $TargetDir
    $WizShortcut.Description = "Install, Repair, or Uninstall Aurora Borealis"
    if (Test-Path $IcoPath) { $WizShortcut.IconLocation = "$IcoPath,0" }
    $WizShortcut.Save()
}

if ($DoDesktopShortcut) {
    $DesktopDir = [Environment]::GetFolderPath("Desktop")
    $DeskShortcut = $WshShell.CreateShortcut((Join-Path $DesktopDir "Aurora Borealis.lnk"))
    $DeskShortcut.TargetPath = $LauncherPath
    $DeskShortcut.WorkingDirectory = $TargetDir
    $DeskShortcut.Description = "Aurora Borealis - D&D 5e / 5.5e Character & Companion Builder"
    if (Test-Path $IcoPath) { $DeskShortcut.IconLocation = "$IcoPath,0" }
    $DeskShortcut.Save()
    Write-Host "Created Desktop shortcut in $DesktopDir"
}

if ($DoFileAssociations) {
    Write-Host "[5/5] Registering .dnd5e, .dnd55e, and .dndcomp file associations (HKCU)..."
    $ProgId = "AuroraBorealis.CharacterFile"
    $CmdStr = "`"$LauncherPath`" --open `"%1`""
    $ClsBase = "Registry::HKEY_CURRENT_USER\Software\Classes"

    New-Item -Path "$ClsBase\$ProgId" -Force | Out-Null
    Set-Item -Path "$ClsBase\$ProgId" -Value "Aurora Borealis Character / Companion File"
    if (Test-Path $IcoPath) {
        New-Item -Path "$ClsBase\$ProgId\DefaultIcon" -Force | Out-Null
        Set-Item -Path "$ClsBase\$ProgId\DefaultIcon" -Value "`"$IcoPath`",0"
    }
    New-Item -Path "$ClsBase\$ProgId\shell\open\command" -Force | Out-Null
    Set-Item -Path "$ClsBase\$ProgId\shell\open\command" -Value $CmdStr

    foreach ($ext in @(".dnd5e", ".dnd55e", ".dndcomp")) {
        New-Item -Path "$ClsBase\$ext" -Force | Out-Null
        Set-Item -Path "$ClsBase\$ext" -Value $ProgId
    }
} else {
    Write-Host "[5/5] Skipping file associations."
}

$UninstallKey = "Registry::HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Uninstall\AuroraBorealis"
New-Item -Path $UninstallKey -Force | Out-Null
Set-ItemProperty -Path $UninstallKey -Name "DisplayName" -Value "Aurora Borealis (D&D 5e / 5.5e)"
Set-ItemProperty -Path $UninstallKey -Name "DisplayVersion" -Value "0.1.0"
Set-ItemProperty -Path $UninstallKey -Name "Publisher" -Value "Aurora Borealis"
Set-ItemProperty -Path $UninstallKey -Name "InstallLocation" -Value $TargetDir
Set-ItemProperty -Path $UninstallKey -Name "UninstallString" -Value "powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$TargetDir\installer\windows_wizard.ps1`" -InitialAction Uninstall"
if (Test-Path $IcoPath) { Set-ItemProperty -Path $UninstallKey -Name "DisplayIcon" -Value "$IcoPath,0" }

# Notify Windows Explorer to refresh shortcut & file association icon cache immediately
try {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class AuroraShellNotify {
    [DllImport("shell32.dll")]
    public static extern void SHChangeNotify(int wEventId, int uFlags, IntPtr dwItem1, IntPtr dwItem2);
}
"@ -ErrorAction SilentlyContinue
    [AuroraShellNotify]::SHChangeNotify(0x08000000, 0x0000, [IntPtr]::Zero, [IntPtr]::Zero)
} catch {}

$InstalledPacks = @()
if ($InstallAuroraLegacy) {
    Write-Host "[Content] Downloading & installing official Aurora Legacy content from GitHub..."
    Invoke-NativeChecked { & $VenvPy -u -m aurora_borealis.main --sync-official } "Sync Aurora Legacy content"
    $InstalledPacks += "Aurora Legacy"
}
if ($InstallFiveTools) {
    Write-Host "[Content] Downloading & converting 5e.tools D&D 5e/5.5e content from GitHub..."
    Invoke-NativeChecked { & $VenvPy -u -m aurora_borealis.main --sync-5etools } "Sync 5e.tools content"
    $InstalledPacks += "5e.tools"
}
$PackSummary = if ($InstalledPacks.Count -gt 0) { $InstalledPacks -join ", " } else { "On-demand in app" }

Write-Host ""
Write-Host "Aurora Borealis setup complete!" -ForegroundColor Green
Write-Host "  Installed in : $TargetDir"
Write-Host "  Start Menu   : Aurora Borealis"
Write-Host "  File Types   : .dnd5e, .dnd55e, .dndcomp"
Write-Host "  Content Packs: $PackSummary"
