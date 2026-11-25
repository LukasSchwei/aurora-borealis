; Inno Setup script to build a standalone Windows AuroraBorealis-Setup.exe
; Build first with: packaging\windows\build-windows-installer.ps1

#define MyAppName "Aurora Borealis"
#define MyAppVersion "0.2.0"
#define MyAppPublisher "Aurora Borealis"
#define MyAppExeName "AuroraBorealis.exe"

[Setup]
AppId={{8F9B4E4A-2C3E-4D12-9F5B-7B4B6B7C8824}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Aurora Borealis
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
ChangesAssociations=yes
OutputDir=..\..\dist
OutputBaseFilename=AuroraBorealis-Setup-{#MyAppVersion}
SetupIconFile=..\..\aurora_borealis\assets\aurora-borealis.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "assoc"; Description: "Register .dnd5e, .dnd55e, and .dndcomp file associations"; GroupDescription: "File Associations"

[Files]
Source: "..\..\dist\AuroraBorealis\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.dnd5e"; ValueType: string; ValueName: ""; ValueData: "AuroraBorealisFile"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.dnd55e"; ValueType: string; ValueName: ""; ValueData: "AuroraBorealisFile"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.dndcomp"; ValueType: string; ValueName: ""; ValueData: "AuroraBorealisFile"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\AuroraBorealisFile"; ValueType: string; ValueName: ""; ValueData: "Aurora Borealis Character / Companion File"; Flags: uninsdeletekey; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\AuroraBorealisFile\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\AuroraBorealisFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" --open ""%1"""; Tasks: assoc

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
