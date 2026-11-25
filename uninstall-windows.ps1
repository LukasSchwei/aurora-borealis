param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "Aurora Borealis\app")
)

$ErrorActionPreference = "SilentlyContinue"
$StartMenuShortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Aurora Borealis.lnk"
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Aurora Borealis.lnk"

if (Test-Path $StartMenuShortcut) { Remove-Item -Force $StartMenuShortcut }
if (Test-Path $DesktopShortcut) { Remove-Item -Force $DesktopShortcut }

$ClsBase = "Registry::HKEY_CURRENT_USER\Software\Classes"
foreach ($ext in @(".dnd5e", ".dnd55e", ".dndcomp")) {
    Remove-Item -Recurse -Force "$ClsBase\$ext"
}
Remove-Item -Recurse -Force "$ClsBase\AuroraBorealis.CharacterFile"
Remove-Item -Recurse -Force "Registry::HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Uninstall\AuroraBorealis"

if (Test-Path $InstallDir) {
    Remove-Item -Recurse -Force $InstallDir
}

Write-Host "Aurora Borealis uninstalled. Your saved characters in Documents were kept."
