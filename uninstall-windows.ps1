param(
    [string]$InstallDir = "",
    [switch]$PurgeConfig
)

$ErrorActionPreference = "SilentlyContinue"
$UninstallKey = "Registry::HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Uninstall\AuroraBorealis"

if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    if (Test-Path $UninstallKey) {
        $regLoc = (Get-ItemProperty -Path $UninstallKey -Name "InstallLocation").InstallLocation
        if (-not [string]::IsNullOrWhiteSpace($regLoc)) {
            $InstallDir = $regLoc
        }
    }
    if ([string]::IsNullOrWhiteSpace($InstallDir)) {
        $InstallDir = Join-Path $env:LOCALAPPDATA "Aurora Borealis\app"
    }
}

Write-Host "=== Aurora Borealis Windows Uninstaller ===" -ForegroundColor Cyan
Write-Host "[1/4] Removing Start Menu and Desktop shortcuts..."
$StartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$StartMenuShortcut = Join-Path $StartMenuDir "Aurora Borealis.lnk"
$WizardShortcut = Join-Path $StartMenuDir "Aurora Borealis Setup Wizard.lnk"
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Aurora Borealis.lnk"

if (Test-Path $StartMenuShortcut) { Remove-Item -Force $StartMenuShortcut }
if (Test-Path $WizardShortcut) { Remove-Item -Force $WizardShortcut }
if (Test-Path $DesktopShortcut) { Remove-Item -Force $DesktopShortcut }

Write-Host "[2/4] Removing file associations & Uninstall registry entry..."
$ClsBase = "Registry::HKEY_CURRENT_USER\Software\Classes"
foreach ($ext in @(".dnd5e", ".dnd55e", ".dndcomp")) {
    Remove-Item -Recurse -Force "$ClsBase\$ext"
}
Remove-Item -Recurse -Force "$ClsBase\AuroraBorealis.CharacterFile"
Remove-Item -Recurse -Force $UninstallKey

Write-Host "[3/4] Removing application directory ($InstallDir)..."
if (Test-Path $InstallDir) {
    Remove-Item -Recurse -Force $InstallDir
}

if ($PurgeConfig) {
    Write-Host "[4/4] Removing user configuration & cached content (Documents kept)..."
    $AppDataCfg = Join-Path $env:APPDATA "Aurora Borealis"
    $LocalCache = Join-Path $env:LOCALAPPDATA "Aurora Borealis"
    if (Test-Path $AppDataCfg) { Remove-Item -Recurse -Force $AppDataCfg }
    if (Test-Path $LocalCache) { Remove-Item -Recurse -Force $LocalCache }
} else {
    Write-Host "[4/4] Preserving user configuration and saved characters."
}

Write-Host "Aurora Borealis uninstalled. Your saved characters in Documents were kept." -ForegroundColor Green
