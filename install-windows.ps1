param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "Aurora Borealis\app"),
    [switch]$InPlace,
    [switch]$CreateDesktopShortcut = $true,
    [switch]$RegisterFileAssociations = $true,
    [switch]$SkipWinget,
    [switch]$InstallAuroraLegacy,
    [switch]$InstallFiveTools
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

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
        & winget install --id Python.Python.3.12 -e --source winget --scope user --accept-package-agreements --accept-source-agreements
        $env:PATH = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
        $PythonCmd = Find-Python310
    }
    if (-not $PythonCmd) {
        Write-Error "Python 3.10+ is required. Install Python 3 from https://www.python.org/downloads/windows/ and re-run install-windows.bat."
    }
}
Write-Host "[1/5] Using Python: $($PythonCmd -join ' ')"

if (-not $SkipWinget -and -not (Get-Command 7z -ErrorAction SilentlyContinue) -and -not (Test-Path "C:\Program Files\7-Zip\7z.exe")) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Optional: installing 7-Zip via winget for Aurora .msi extraction..."
        try {
            & winget install --id 7zip.7zip -e --source winget --accept-package-agreements --accept-source-agreements
        } catch {
            Write-Warning "Could not install 7-Zip automatically; Aurora GitHub/5e.tools features still work without it."
        }
    }
}

if ($InPlace) {
    $TargetDir = $ScriptDir
    Write-Host "[2/5] Installing in-place at $TargetDir"
} else {
    $TargetDir = $InstallDir
    Write-Host "[2/5] Copying Aurora Borealis files to $TargetDir..."
    New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
    $ItemsToCopy = @(
        "aurora_borealis",
        "aurora-borealis.bat",
        "aurora-borealis.ps1",
        "install-windows.ps1",
        "install-windows.bat",
        "uninstall-windows.ps1",
        "setup-wizard-windows.ps1",
        "setup-wizard-windows.bat",
        "pyproject.toml",
        "requirements.txt",
        "README.md"
    )
    foreach ($item in $ItemsToCopy) {
        $src = Join-Path $ScriptDir $item
        if (Test-Path $src) {
            $dst = Join-Path $TargetDir $item
            if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
            Copy-Item -Recurse -Force $src $dst
        }
    }
}

Write-Host "[3/5] Creating virtual environment and installing dependencies (PySide6, lxml, pypdf)..."
$VenvDir = Join-Path $TargetDir ".venv"
if ($PythonCmd.Count -eq 2) {
    & $PythonCmd[0] $PythonCmd[1] -m venv $VenvDir
} else {
    & $PythonCmd[0] -m venv $VenvDir
}
$VenvPy = Join-Path $VenvDir "Scripts\python.exe"
& $VenvPy -m pip install --upgrade pip setuptools wheel
& $VenvPy -m pip install -r (Join-Path $TargetDir "requirements.txt")
& $VenvPy -m pip install --no-deps --no-build-isolation -e $TargetDir

Write-Host "[4/5] Generating application icon (.ico) and shortcuts..."
$SvgPath = Join-Path $TargetDir "aurora_borealis\assets\aurora-borealis.svg"
$IcoPath = Join-Path $TargetDir "aurora_borealis\assets\aurora-borealis.ico"
if (Test-Path $SvgPath) {
    $IconGenScript = @'
import struct, sys
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QIcon
app = QGuiApplication.instance() or QGuiApplication([])
icon = QIcon(sys.argv[1])
pix = icon.pixmap(256, 256)
if not pix.isNull():
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pix.save(buf, "PNG")
    png = bytes(buf.data())
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 6 + 16)
    with open(sys.argv[2], "wb") as f:
        f.write(header + entry + png)
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

if ($CreateDesktopShortcut) {
    $DesktopDir = [Environment]::GetFolderPath("Desktop")
    $DeskShortcut = $WshShell.CreateShortcut((Join-Path $DesktopDir "Aurora Borealis.lnk"))
    $DeskShortcut.TargetPath = $LauncherPath
    $DeskShortcut.WorkingDirectory = $TargetDir
    $DeskShortcut.Description = "Aurora Borealis - D&D 5e / 5.5e Character & Companion Builder"
    if (Test-Path $IcoPath) { $DeskShortcut.IconLocation = "$IcoPath,0" }
    $DeskShortcut.Save()
    Write-Host "Created Desktop shortcut in $DesktopDir"
}

if ($RegisterFileAssociations) {
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
Set-ItemProperty -Path $UninstallKey -Name "DisplayVersion" -Value "0.2.0"
Set-ItemProperty -Path $UninstallKey -Name "Publisher" -Value "Aurora Borealis"
Set-ItemProperty -Path $UninstallKey -Name "InstallLocation" -Value $TargetDir
Set-ItemProperty -Path $UninstallKey -Name "UninstallString" -Value "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$TargetDir\setup-wizard-windows.ps1`" -InitialAction Uninstall"
if (Test-Path $IcoPath) { Set-ItemProperty -Path $UninstallKey -Name "DisplayIcon" -Value "$IcoPath,0" }

$InstalledPacks = @()
if ($InstallAuroraLegacy) {
    Write-Host "[Content] Downloading & installing official Aurora Legacy content from GitHub..."
    & $VenvPy -u -m aurora_borealis.main --sync-official
    $InstalledPacks += "Aurora Legacy"
}
if ($InstallFiveTools) {
    Write-Host "[Content] Downloading & converting 5e.tools D&D 5e/5.5e content from GitHub..."
    & $VenvPy -u -m aurora_borealis.main --sync-5etools
    $InstalledPacks += "5e.tools"
}
$PackSummary = if ($InstalledPacks.Count -gt 0) { $InstalledPacks -join ", " } else { "On-demand in app" }

Write-Host ""
Write-Host "Aurora Borealis setup complete!" -ForegroundColor Green
Write-Host "  Installed in : $TargetDir"
Write-Host "  Start Menu   : Aurora Borealis"
Write-Host "  File Types   : .dnd5e, .dnd55e, .dndcomp"
Write-Host "  Content Packs: $PackSummary"
